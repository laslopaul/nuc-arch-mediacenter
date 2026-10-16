#!/bin/bash
set -euo pipefail
# Ansible also executes modules as the managed, unprivileged user.
umask 022
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
venv_dir=${1:-"$repo_dir/.venv"}
# uv supplies the same Python version on Arch and CI.
if command -v uv >/dev/null; then
    # Keep the interpreter outside root's private data directory. Recreate the
    # venv so existing Python symlinks are updated to this shared installation.
    export UV_PYTHON_INSTALL_DIR="${venv_dir}-python"
    export UV_PYTHON_PREFERENCE=only-managed
    uv venv --python 3.13 --clear "$venv_dir"
    uv pip install --python "$venv_dir/bin/python" -r "$repo_dir/requirements-dev.txt"
    chmod -R a+rX "$UV_PYTHON_INSTALL_DIR"
elif command -v python3.13 >/dev/null; then
    python3.13 -m venv "$venv_dir"
    "$venv_dir/bin/python" -m pip install -r "$repo_dir/requirements-dev.txt"
else
    cat >&2 <<'EOF'
Bootstrap requires uv or Python 3.13.
On Arch Linux, run as root:
  pacman -Syu --needed uv
Then run this bootstrap command again. uv will download Python 3.13.
EOF
    exit 1
fi
chmod -R a+rX "$venv_dir"
ANSIBLE_LOCAL_TEMP="$repo_dir/.ansible/tmp" "$venv_dir/bin/ansible-galaxy" collection install \
    -r "$repo_dir/requirements.yml" -p "$venv_dir/collections"
echo "Environment ready: $venv_dir"
