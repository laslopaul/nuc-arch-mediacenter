# nuc-arch-mediacenter

Ansible configuration for Intel NUC mediacenter running on Arch Linux.

## Components

1. labwc Wayland compositor + Alacritty terminal emulator
2. Pipewire audio server
3. Zerotier virtual LAN + dnsmasq DNS server
4. Kodi
5. Firefox
6. Docker applications (TBD)

## Install base system

Boot from Arch Linux installation medium and run `arch-install.sh` script from this repo:

```bash
ROOT_PASSWORD="mypassword" ZEROTIER_NET_ID="8056c2e21c000001" bash arch-install.sh
```

## Apply configuration

After booting to the base system, pass the password for `kodi` user in `KODI_PASSWORD` env variable, and initialize `ansible-pull`:

```bash
# export KODI_PASSWORD="mypassword"
# ansible-pull -U https://github.com/laslopaul/nuc-arch-mediacenter
```

Later on, `ansible-pull` will automatically update configuration every 10 minutes via systemd service.
