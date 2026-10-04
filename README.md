# nuc-arch-mediacenter

Ansible configuration for an Intel NUC mediacenter & home server running Arch Linux.

The machine configures itself with `ansible-pull`: a systemd timer pulls this repo every 10 minutes and applies [local.yml](local.yml) to `localhost`.

## Components

| Role | What it sets up |
| --- | --- |
| `base` | `ansible-pull` timer, `kodi` user (sudo, SSH key, tty1 autologin, Polkit power rules), and optional components: udiskie automount, PipeWire audio, dnsmasq DNS server for the Zerotier LAN, reflector mirrorlist refresh |
| `gui` | labwc (Wayland) or i3 (Xorg) desktop, plus optional apps: Kodi, Firefox, Alacritty |
| `docker` | Docker with a weekly image cleanup timer, and these services: |

Docker services, all deployed with Docker Compose under `~/docker/<service>`:

| Service | Address |
| --- | --- |
| Step CA (private certificate authority) | `https://<domain>:9000` |
| Traefik (reverse proxy, TLS from Step CA, and Let's Encrypt for `<public_domain>`) | port 443 |
| qBittorrent | `https://qb.<domain>` |
| Vaultwarden | `https://vw.<domain>` |
| Plex | host network, port 32400 |
| Immich | `https://immich.<domain>` |
| Syncthing | `https://sync.<domain>` |

The services behind Traefik also answer on `<public_domain>` (e.g. `https://vw.<public_domain>`).

`<domain>` is `nuc-server.lan` by default. dnsmasq resolves it and all its subdomains to the server's Zerotier IP.

## Install base system

1. Boot from the Arch Linux installation medium.
2. Check the configuration block at the top of [arch-install.sh](arch-install.sh): disk, hostname, locale, timezone and static IP settings.
   `DISK_SETUP=1` repartitions the disk from scratch and **wipes all data**. With the default `0`, only the EFI and root volumes are reformatted and `/home` is kept.
3. Run the script:

   ```bash
   ROOT_PASSWORD="mypassword" ZEROTIER_NET_ID="8056c2e21c000001" bash arch-install.sh
   ```

4. Authorize the device ID printed by the script in Zerotier Central, then reboot.

The script installs the base system with LVM, GRUB (UEFI), systemd-networkd with a static IP, Zerotier, and Ansible itself.

## Apply configuration

After booting into the new system, as root, pass the password for the `kodi` user in `KODI_PASSWORD` and run `ansible-pull` once:

```bash
export KODI_PASSWORD="mypassword"
ansible-pull -U https://github.com/laslopaul/nuc-arch-mediacenter
```

The first run installs the `ansible-pull` timer. From then on the configuration is re-applied every 10 minutes, so changes pushed to this repo reach the machine automatically.

The `docker` role expects the Step CA admin provisioner password in `/home/kodi/pki/admin.txt`, to issue Traefik's wildcard certificate.

Traefik also gets a Let's Encrypt wildcard certificate for `*.<public_domain>` (without the apex domain) through a DNS-01 challenge with Spaceship DNS. It needs a Spaceship API key with DNS records read & write access in `/home/kodi/docker/traefik/.env`:

```bash
SPACESHIP_API_KEY=...
SPACESHIP_API_SECRET=...
```

### Running only part of the configuration

Every role and task file has a tag:

```bash
ansible-pull -U https://github.com/laslopaul/nuc-arch-mediacenter --tags gui
```

| Role | Tags |
| --- | --- |
| `base` | `base`, `ansible-pull`, `user`, `udiskie`, `pipewire`, `dnsmasq`, `reflector` |
| `gui` | `gui`, `gui-install`, `gui-config`, `gui-remove` |
| `docker` | `docker`, `docker-install`, `step-ca`, `traefik`, `qb`, `vw`, `plex`, `immich`, `syncthing` |

## Configuration

Shared variables are in [group_vars/all.yml](group_vars/all.yml):

| Variable | Default | Description |
| --- | --- | --- |
| `username` | `kodi` | Main user |
| `domain` | `nuc-server.lan` | Domain for the services |
| `public_domain` | `laslopaul.dev` | Public domain with a Let's Encrypt wildcard certificate |
| `zerotier_ip` | `172.27.100.100` | Server's Zerotier IP; dnsmasq listens on it |

Role defaults, which can be overridden in `group_vars/all.yml`:

- [roles/base/defaults/main.yml](roles/base/defaults/main.yml): SSH public key, repo URL, components, reflector mirror settings
- [roles/gui/defaults/main.yml](roles/gui/defaults/main.yml): desktop, apps and their packages & config paths
- [roles/docker/defaults/main.yml](roles/docker/defaults/main.yml): Docker image versions, timezone

### Selecting base components

```yaml
base_components:
  - udiskie
  - pipewire
  - dnsmasq
  - reflector
base_purge_packages: true
```

A component left out of `base_components` gets its services stopped & disabled, its config removed and its packages uninstalled. Packages still required by another installed package are kept. Set `base_purge_packages: false` to keep the packages installed and only disable and unconfigure the component.

Things to keep in mind:

- Removing `dnsmasq` stops DNS for `<domain>` on the Zerotier LAN.
- The desktop autostart configs launch `udiskie`, so it fails to start if udiskie is removed.
- `fstrim.timer` is enabled by the udiskie tasks.

### Selecting desktop & apps

```yaml
desktop: labwc        # i3, labwc or none
gui_components:
  - kodi
  - firefox
  - alacritty
gui_purge_packages: true
gui_purge_userdata: true
```

The desktop not selected and any app left out of `gui_components` are removed completely:

- their config is deleted
- their packages are uninstalled, except those still required by another package or by a selected desktop or app (`gui_purge_packages`)
- their user data is deleted: `~/.kodi` (Kodi library & addons) and `~/.mozilla` (Firefox profile) (`gui_purge_userdata`). **This can't be undone**, and since `ansible-pull` runs every 10 minutes, it happens shortly after the change is pushed.

With the default `desktop: labwc`, this also means the i3 config and the i3/Xorg packages are removed if they were installed.

Set `gui_purge_packages: false` to keep packages installed, and `gui_purge_userdata: false` to keep user data, so an app can be brought back with its library and profile intact.

To remove the GUI completely:

```yaml
desktop: none
gui_components: []
```

The desktop autostart configs launch Firefox and Alacritty. If you remove those apps but keep a desktop, the desktop fails to start them on login.

## Maintenance

- [Renovate](renovate.json) runs daily in GitHub Actions and opens PRs for new versions of the Docker images in [roles/docker/defaults/main.yml](roles/docker/defaults/main.yml) and of GitHub Actions. Minor and patch updates are merged automatically, and `ansible-pull` then deploys them.
- `ansible-lint` runs on pull requests that change Ansible files.
- `docker-cleanup.timer` removes all unused Docker images every Sunday at 03:00.
