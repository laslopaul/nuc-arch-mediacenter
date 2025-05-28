# nuc-arch-mediacenter

Ansible configuration for Intel NUC mediacenter running on Arch Linux.

## Components

1. i3 window manager + Alacritty terminal emulator
2. Pipewire audio server
3. Kodi
4. Firefox
5. Docker applications (TBD)

## Install base system

Boot from Arch Linux installation medium and run `arch-install.sh` script from this repo:

```bash
ROOT_PASSWORD="mypassword" bash arch-install.sh
```

## Apply configuration

After booting to the base system, pass the password for `kodi` user in `KODI_PASSWORD` env variable, and initialize `ansible-pull`:

```bash
# export KODI_PASSWORD="mypassword"
# ansible-pull -U https://github.com/laslopaul/nuc-arch-mediacenter
```

Later on, `ansible-pull` will automatically update configuration every 10 minutes via systemd service.
