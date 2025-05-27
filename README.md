# nuc-arch-mediacenter

Ansible configuration for Intel NUC mediacenter running on Arch Linux.

## Components

1. Kodi
2. Firefox
3. Docker applications (TBD)

## Installation

The configuration is based on `ansible-pull`, so the following dependencies should be installed on the target machine:

```bash
# pacman -Sy ansible git python-passlib
```

Then you should pass the password for `kodi` user in `KODI_PASSWORD` env variable, and initialize `ansible-pull`:

```bash
# export KODI_PASSWORD="mypassword"
# ansible-pull -U https://github.com/laslopaul/nuc-arch-mediacenter
```
