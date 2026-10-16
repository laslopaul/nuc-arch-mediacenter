# nuc-arch-mediacenter

Ansible configuration for an Intel NUC mediacenter & home server running Arch Linux.

The machine configures itself with `ansible-pull`: a systemd timer pulls this repo every 10 minutes and applies [local.yml](local.yml) to `localhost`.

## Components

| Role | What it sets up |
| --- | --- |
| `base` | IPv6 disabled, `ansible-pull` timer, `kodi` user (sudo, SSH key, tty1 autologin, Polkit power rules), and optional components: removable drive automounting with udev-media-automount, PipeWire audio, dnsmasq DNS server for the Zerotier LAN, reflector mirrorlist refresh |
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

After booting into the new system, as root, clone the repository and bootstrap the pinned Ansible environment. The installer provides `uv`; bootstrap uses it to install Python 3.13. On a development machine, an existing `python3.13` also works.

```bash
git clone https://github.com/laslopaul/nuc-arch-mediacenter /root/nuc-arch-mediacenter
cd /root/nuc-arch-mediacenter
bash scripts/bootstrap.sh /opt/nuc-ansible
export KODI_PASSWORD="mypassword"
/opt/nuc-ansible/bin/ansible-pull -U https://github.com/laslopaul/nuc-arch-mediacenter
```

**Existing installations:** install `uv` if neither `uv` nor `python3.13` is available, then run the bootstrap command before deploying this refactor. The timer now uses `/opt/nuc-ansible/bin/ansible-pull`. The playbook checks that runtime exists before changing the timer. Re-run bootstrap when either requirements file changes; dependency upgrades are explicit rather than performed by the ten-minute timer.

On an existing Arch installation, run as root from the repository directory:

```bash
pacman -Syu --needed uv
bash scripts/bootstrap.sh /opt/nuc-ansible
```

The first run installs the `ansible-pull` timer. From then on the configuration is re-applied every 10 minutes, so changes pushed to this repo reach the machine automatically.

The `docker` role expects the Step CA admin provisioner password in `/home/kodi/pki/admin.txt`, to issue Traefik's wildcard certificate.

Traefik also gets a Let's Encrypt wildcard certificate for `*.<public_domain>` (without the apex domain) through a DNS-01 challenge with Spaceship DNS. It needs a Spaceship API key with DNS records read & write access in `/home/kodi/docker/traefik/.env`:

```bash
SPACESHIP_API_KEY=...
SPACESHIP_API_SECRET=...
```

### Running only part of the configuration

Roles and components retain their existing tags, including `qb` and `vw`:

```bash
/opt/nuc-ansible/bin/ansible-pull -U https://github.com/laslopaul/nuc-arch-mediacenter --tags gui
```

| Role | Tags |
| --- | --- |
| `base` | `base`, `ipv6`, `ansible-pull`, `user`, `udev-media-automount`, `pipewire`, `dnsmasq`, `reflector` |
| `gui` | `gui`, `gui-install`, `gui-config`, `gui-remove` |
| `docker` | `docker`, `docker-install`, `step-ca`, `traefik`, `qb`, `vw`, `plex`, `immich`, `syncthing`, `docker-remove` |

## Configuration

Shared variables are in [group_vars/all.yml](group_vars/all.yml):

| Variable | Default | Description |
| --- | --- | --- |
| `username` | `kodi` | Main user |
| `domain` | `nuc-server.lan` | Domain for the services |
| `public_domain` | `laslopaul.dev` | Public domain with a Let's Encrypt wildcard certificate |
| `managed_user_home` | `/home/{{ username }}` | Managed account home |
| `media_path` | `{{ managed_user_home }}/Library` | Shared media location |
| `pki_path` | `{{ managed_user_home }}/pki` | Step CA client state and provisioner password |
| `ansible_runtime_path` | `/opt/nuc-ansible` | Pinned Ansible virtual environment |
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
```

The desktop not selected and any app left out of `gui_components` have their managed configuration removed. With `gui_purge_packages: true`, packages are uninstalled only when no remaining package requires them, and packages belonging to selected components are explicitly protected.

User data such as `~/.kodi` and `~/.mozilla` is always retained by normal reconciliation. Use [purge.yml](purge.yml) to delete it explicitly. The old `gui_purge_userdata` setting is no longer used.

To remove the GUI completely:

```yaml
desktop: none
gui_components: []
```

Desktop startup templates launch only selected apps. PipeWire setup in startup scripts is conditional on the base component being selected; the legacy udiskie startup commands have been removed.

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
```

A service left out of `docker_services` is stopped, its containers are removed with `docker compose down`, and its compose file is deleted. On top of that:

- its images are deleted (`docker_purge_images`)
- removing `step-ca` also removes the `step` symlink, and uninstalls `step-cli` (`docker_purge_packages`)
- removing `traefik` also stops and removes `traefik-cert-renewer.service`
Service directories, secrets, databases, media libraries, named volumes and CA trust are retained. Data deletion is handled only by [purge.yml](purge.yml); the old `docker_purge_data` setting is no longer used.

Services are checked for dependencies before anything is changed: qBittorrent, Vaultwarden, Immich and Syncthing need `traefik`, and `traefik` needs `step-ca`. Removal runs in reverse order (apps, then Traefik, then Step CA).

To add a service with a plain Docker Compose deployment:

1. Add `roles/docker/templates/<service>-compose.yml.j2`.
2. Add its directory, Compose project name, named volumes, subdirectories, dependencies, template and tag to `docker_service_catalog` in [Docker defaults](roles/docker/defaults/main.yml). Named volumes must be listed explicitly for targeted purging.
3. Add it to `docker_service_order` after its dependencies, and to `docker_services` when it should be enabled. Add image references to `images` for Renovate.

Deployment follows `docker_service_order`; removal reverses that order. Step CA and Traefik keep their specialized setup tasks. Selection and dependency checks run before Docker changes.

To remove Docker, set `docker_enabled: false`. Reconciliation stops the managed services, disables Docker and its cleanup timer, and optionally removes its packages. All retained data survives.

## Explicit data purging

First disable the target in configuration and apply `local.yml`. Then run the purge playbook with exact targets:

```bash
/opt/nuc-ansible/bin/ansible-playbook purge.yml -e '{"purge_gui_targets": ["kodi", "firefox"]}'
/opt/nuc-ansible/bin/ansible-playbook purge.yml -e '{"purge_docker_targets": ["immich"]}'
```

Purging permanently deletes the selected app profiles or service directory, including its databases, `.env` secrets and CA keys where applicable. Named volumes are removed by explicit catalog names, even after reconciliation has deleted the Compose file. A service with named volumes needs a running Docker daemon for targeted purging; keep `docker_enabled: true` while disabling that service. Existing containers for the selected Compose project must already be removed.

To delete **all** Docker engine storage, including unmanaged containers, images and volumes, first apply `docker_enabled: false`, then explicitly select every service and engine storage:

```bash
/opt/nuc-ansible/bin/ansible-playbook purge.yml -e '{"purge_docker_targets": ["step-ca", "traefik", "qbittorrent", "vaultwarden", "plex", "immich", "syncthing"], "purge_docker_engine_data": true}'
```

No targets are selected by default. Enabled components cannot be purged. Purging does not delete `media_path`. Inspect planned deletions with `--check --diff` before running the command without check mode.

## Development and validation

```bash
bash scripts/bootstrap.sh
export PATH="$PWD/.venv/bin:$PATH"
ansible-lint --offline
ansible-playbook local.yml --syntax-check
ansible-playbook purge.yml --syntax-check
python -m unittest discover -s tests -v
```

The shared environment pins Python tooling and collections. Compose tests need the Docker CLI with Compose, but no daemon; they render all service templates with fixture secrets and validate the results using `docker compose config`. Other checks cover dependency validation, desktop startup selection, cleanup failure propagation, check mode, and shared-package preservation.

For lifecycle and idempotence checks on a **disposable Arch Linux VM**, prepare a Python 3.13 interpreter on the VM (for example with `uv venv --python 3.13 /opt/nuc-ansible`), and provide an SSH inventory with the VM in `[local]` (do not use the production inventory):

```ini
[local]
arch-refactor-vm ansible_host=192.0.2.10 ansible_user=root ansible_python_interpreter=/opt/nuc-ansible/bin/python
```

```bash
python tests/arch-vm/run.py /path/to/disposable-vm-inventory
```

The scenario creates `ansible-refactor-test`, installs i3 and Alacritty, verifies unchanged second runs, removes Alacritty while preserving i3's shared font and a Firefox profile sentinel, then exercises explicit profile purging. It leaves test state on the disposable VM. It does not run the base role or change the production user.

Base tasks are organized by component under `roles/base/tasks/<component>/{present,absent}.yml`; legacy cleanup is under `migrations/`. User UID/GID resolution lives in `user_identity`, and package removal is shared through `package_cleanup`. The cleanup helper removes only nominated packages without reverse dependencies, repeats until stable, and never recursively removes unrelated dependencies. In check mode it reports currently removable leaf packages without simulating the entire dependency cascade.

## Maintenance

- [Renovate](renovate.json) runs daily in GitHub Actions and opens PRs for new versions of the Docker images in [roles/docker/defaults/main.yml](roles/docker/defaults/main.yml), GitHub Actions, Ansible Galaxy collections in [requirements.yml](requirements.yml), and Python packages in [requirements-dev.txt](requirements-dev.txt). Minor and patch updates are merged automatically. `ansible-pull` deploys playbook changes; re-run `bash scripts/bootstrap.sh /opt/nuc-ansible` to install updates to either requirements file.
- CI runs lint, playbook syntax checks and behavior/Compose validation for changes to Ansible, scripts and tests. The Arch VM scenario is run separately against a disposable VM.
- `docker-cleanup.timer` removes all unused Docker images every Sunday at 03:00.
