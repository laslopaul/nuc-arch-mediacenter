# nuc-arch-mediacenter

Ansible configuration for an Intel NUC mediacenter & home server running Arch Linux.

The machine configures itself with `ansible-pull`: a systemd timer pulls this repo every 10 minutes and applies [local.yml](local.yml) to `localhost`.

## Components

| Role | What it sets up |
| --- | --- |
| `base` | `ansible-pull` timer, `kodi` user (sudo, SSH key, tty1 autologin, Polkit power rules), and optional components: removable drive automounting with udev-media-automount, PipeWire audio, dnsmasq DNS server for the Zerotier LAN, reflector mirrorlist refresh |
| `gui` | labwc (Wayland) or i3 (Xorg) desktop, plus optional apps: Kodi, Firefox, Alacritty |
| `docker` | Docker with a weekly image cleanup timer, and optional services: |

Docker services, all deployed with Docker Compose under `~/docker/<folder>`:

| Service | Name in `docker_services` | Address |
| --- | --- | --- |
| Step CA (private certificate authority) | `step-ca` | `https://<domain>:9000` |
| Traefik (reverse proxy, TLS from Step CA, and Let's Encrypt for `<public_domain>`) | `traefik` | port 443 |
| qBittorrent | `qbittorrent` | `https://qb.<domain>` |
| Vaultwarden | `vaultwarden` | `https://vw.<domain>` |
| Plex | `plex` | host network, port 32400 |
| Immich | `immich` | `https://immich.<domain>` |
| Syncthing | `syncthing` | `https://sync.<domain>` |

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
| `base` | `base`, `ansible-pull`, `user`, `udev-media-automount`, `pipewire`, `dnsmasq`, `reflector` |
| `gui` | `gui`, `gui-install`, `gui-config`, `gui-remove` |
| `docker` | `docker`, `docker-install`, `step-ca`, `traefik`, `qb`, `vw`, `plex`, `immich`, `syncthing`, `docker-remove` |

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
- [roles/docker/defaults/main.yml](roles/docker/defaults/main.yml): services, their folders & dependencies, Docker image versions, timezone

### Selecting base components

```yaml
base_components:
  - udev-media-automount
  - pipewire
  - dnsmasq
  - reflector
base_purge_packages: true
```

A component left out of `base_components` gets its services stopped & disabled, its config removed and its packages uninstalled. Packages still required by another installed package are kept. Set `base_purge_packages: false` to keep the packages installed and only disable and unconfigure the component.

Things to keep in mind:

- Removing `dnsmasq` stops DNS for `<domain>` on the Zerotier LAN.
- `fstrim.timer` is enabled by the udev-media-automount tasks.

### Removable drive automounting

The `udev-media-automount` component installs the headless helper from a pinned
[upstream revision](https://github.com/Ferk/udev-media-automount/tree/efca3c5a0548211c84e98de16b41641a961b6273), without the
optional dmenu frontend or any GTK dependencies. `media_automount_revision` in
base defaults controls updates. No AUR build tools are needed on the server.

Udev starts a systemd service for inserted USB filesystems and SD card partitions.
Internal SATA/NVMe disks and encrypted containers are not automatically mounted.
The helper leaves devices listed in `/etc/fstab` alone. Mounts appear under
`/media/<label>.<filesystem>` (or a device name when unlabeled). FAT, exFAT and
NTFS mounts grant the configured `username` write access; Unix filesystems retain
their on-disk ownership. Filesystem drivers/helpers such as `ntfs-3g` must already
be available when needed.

Migration stops the old udiskie user service and removes its configuration and
Polkit rule. With `base_purge_packages: true`, it also removes udiskie, UDisks2 and
their unused dependencies when no other package requires them. Existing mounts
are left in place: reconnect drives or reboot to use the new automounter, and
update any consumers of the old `/run/media/<user>/...` paths. The role reloads
udev rules without triggering all existing devices. Removing the component stops
future automounting without unmounting active drives.

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

### Selecting Docker services

```yaml
docker_enabled: true
docker_services:
  - step-ca
  - traefik
  - qbittorrent
  - vaultwarden
  - plex
  - immich
  - syncthing
docker_purge_images: true
docker_purge_packages: true
docker_purge_data: false
```

A service left out of `docker_services` is stopped, its containers are removed with `docker compose down`, and its compose file is deleted. On top of that:

- its images are deleted (`docker_purge_images`)
- removing `step-ca` also removes the `step` symlink, and uninstalls `step-cli` (`docker_purge_packages`)
- removing `traefik` also stops and removes `traefik-cert-renewer.service`
- with `docker_purge_data: true`, its whole folder under `~/docker` and its named volumes are deleted. That includes its config, databases, `.env` secrets, the **Vaultwarden vault** and the **Immich photo library**, and for `step-ca` the CA keys (its root certificate is also removed from the system trust store). **This can't be undone**, which is why it's off by default. Media in `~/Library` (used by Plex and qBittorrent) is never touched.

Services are checked for dependencies before anything is changed: qBittorrent, Vaultwarden, Immich and Syncthing need `traefik`, and `traefik` needs `step-ca`. Removal runs in reverse order (apps, then Traefik, then Step CA).

To add a service with a plain Docker Compose deployment:

1. Add `roles/docker/templates/<service>-compose.yml.j2`.
2. In [roles/docker/defaults/main.yml](roles/docker/defaults/main.yml), add the service to `docker_services`, `docker_service_dirs` and `images`. Add it to `docker_service_subdirs` if it needs subfolders, and to `docker_service_requires` if it runs behind Traefik.
3. Add an `import_tasks: service.yml` entry with `docker_service: <service>` to [roles/docker/tasks/main.yml](roles/docker/tasks/main.yml).

To remove Docker completely, set `docker_enabled: false`. All services are removed as above, the Docker service and `docker-cleanup.timer` are stopped and disabled, and with `docker_purge_packages` the Docker packages are uninstalled. With `docker_purge_data: true`, `~/docker` and `/var/lib/docker` (all images, containers and volumes, including ones not managed by this repo) are deleted too.

## Maintenance

- [Renovate](renovate.json) runs daily in GitHub Actions and opens PRs for new versions of the Docker images in [roles/docker/defaults/main.yml](roles/docker/defaults/main.yml) and of GitHub Actions. Minor and patch updates are merged automatically, and `ansible-pull` then deploys them.
- `ansible-lint` runs on pull requests that change Ansible files.
- `docker-cleanup.timer` removes all unused Docker images every Sunday at 03:00.
