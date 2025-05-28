#!/bin/bash

set -euo pipefail

# ========== CONFIGURATION ==========
DISK="/dev/sda"
HOSTNAME="nuc-server"
ROOT_PASSWORD=
VGNAME="vg0"
LOCALE="ru_RU.UTF-8"
KEYMAP="us"
TIMEZONE="Europe/Minsk"

# Network config (change these)
INTERFACE="enp3s0"
STATIC_IP="192.168.100.100/24"
GATEWAY="192.168.100.1"
DNS="8.8.8.8"
# ===================================

echo "==> Wiping disk: $DISK"
sgdisk --zap-all "$DISK"

echo "==> Creating GPT partitions"
sgdisk -n1:0:+1G -t1:ef00 "$DISK"
sgdisk -n2:0:0     -t2:8300 "$DISK"

EFI="${DISK}1"
LVM_PART="${DISK}2"

echo "==> Formatting EFI system partition"
mkfs.fat -F32 "$EFI"

echo "==> Setting up LVM"
pvcreate "$LVM_PART"
vgcreate "$VGNAME" "$LVM_PART"
lvcreate -L 100G "$VGNAME" -n root
lvcreate -l 100%FREE "$VGNAME" -n home

echo "==> Formatting logical volumes"
mkfs.ext4 "/dev/$VGNAME/root"
mkfs.ext4 "/dev/$VGNAME/home"

echo "==> Mounting filesystems"
mount "/dev/$VGNAME/root" /mnt
mkdir /mnt/home
mount "/dev/$VGNAME/home" /mnt/home
mkdir /mnt/boot
mount "$EFI" /mnt/boot

echo "==> Installing base system"
pacstrap -K /mnt base linux linux-firmware intel-ucode lvm2 iwd man-db man-pages grub efibootmgr vim htop mc ansible git python-passlib openssh

echo "==> Generating fstab"
genfstab -U /mnt >> /mnt/etc/fstab

echo "==> Configuring system"
arch-chroot /mnt /bin/bash <<EOF
ln -sf /usr/share/zoneinfo/$TIMEZONE /etc/localtime
hwclock --systohc
cat > /etc/systemd/timesyncd.conf.d/local.conf <<END
[Time]
NTP=0.arch.pool.ntp.org 1.arch.pool.ntp.org 2.arch.pool.ntp.org 3.arch.pool.ntp.org
FallbackNTP=0.pool.ntp.org 1.pool.ntp.org 0.by.pool.ntp.org
END
systemctl enable systemd-timesyncd

echo -e "$LOCALE UTF-8\nen_US.UTF-8 UTF-8" > /etc/locale.gen
locale-gen
echo "LANG=$LOCALE" > /etc/locale.conf
echo "KEYMAP=$KEYMAP" > /etc/vconsole.conf

echo "$HOSTNAME" > /etc/hostname

ln -s /usr/bin/vim /bin/vi

echo "root:$ROOT_PASSWORD" | chpasswd

echo "==> Enable systemd-networkd"
systemctl enable systemd-networkd

echo "==> Create static IP config for $INTERFACE"
mkdir -p /etc/systemd/network
cat > /etc/systemd/network/20-wired.network <<END
[Match]
Name=$INTERFACE

[Network]
Address=$STATIC_IP
Gateway=$GATEWAY
DNS=$DNS
END

echo "==> Configuring initramfs for LVM"
sed -i 's/block filesystems/block lvm2 filesystems/' /etc/mkinitcpio.conf
mkinitcpio -P

echo "==> Installing GRUB (UEFI)"
grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=GRUB
grub-mkconfig -o /boot/grub/grub.cfg
EOF

echo "==> Installation complete. You can now reboot."
