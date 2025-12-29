# nuc-arch-mediacenter

Ansible configuration for Intel NUC mediacenter running on Arch Linux.

## Components

1. labwc Wayland compositor + Alacritty terminal emulator
2. Pipewire audio server
3. Zerotier virtual LAN + dnsmasq DNS server
4. Kodi
5. Firefox
6. Docker applications:
    - Traefik
    - Qbittorrent
    - Plex
    - Vaultwarden
    - Nextcloud

## Install base system

Boot from Arch Linux installation medium and run `arch-install.sh` script from this repo:

```bash
ROOT_PASSWORD="mypassword" ZEROTIER_NET_ID="8056c2e21c000001" bash arch-install.sh
```

## Create CA certificate with OpenSSL

Log in as `kodi`, create `ca` folder in its home directory, copy `ca.cnf` from the repo root to this folder and run:

```bash
cd ca
openssl genrsa -out ca.key 4096

openssl req -x509 -new -nodes \
  -key ca.key \
  -sha256 \
  -days 3650 \
  -out ca.crt \
  -config ca.cnf
```

## Apply configuration

After booting to the base system, pass the password for `kodi` user in `KODI_PASSWORD` env variable, and initialize `ansible-pull`:

```bash
# export KODI_PASSWORD="mypassword"
# ansible-pull -U https://github.com/laslopaul/nuc-arch-mediacenter
```

Later on, `ansible-pull` will automatically update configuration every 10 minutes via systemd service.
