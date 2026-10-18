#!/bin/bash
set -euo pipefail
# Ansible also executes modules as the managed, unprivileged user.
umask 022
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
runtime_dir="$repo_dir/.venv"
prune_old_python=false
runtime_argument_seen=false
for argument in "$@"; do
    case "$argument" in
        --prune-old-python) prune_old_python=true ;;
        -h|--help)
            echo "Usage: bash scripts/bootstrap.sh [runtime_dir] [--prune-old-python]"
            exit 0 ;;
        -*) echo "Unknown option: $argument" >&2; exit 2 ;;
        *)
            if [ "$runtime_argument_seen" = true ]; then
                echo "Only one runtime directory may be specified." >&2
                exit 2
            fi
            runtime_dir="$argument"
            runtime_argument_seen=true ;;
    esac
done
mkdir -p "$runtime_dir"
runtime_dir=$(cd -- "$runtime_dir" && pwd)
chmod a+rx "$runtime_dir"
venv_dir="$runtime_dir/venv"
# uv supplies the same Python version on Arch and CI.
if command -v uv >/dev/null; then
    # Keep the interpreter outside root's private data directory. Recreate the
    # venv so existing Python symlinks are updated to this shared installation.
    export UV_PYTHON_INSTALL_DIR="$runtime_dir/python"
    export UV_PYTHON_PREFERENCE=only-managed
    uv venv --python 3.15 --clear "$venv_dir"
    uv pip install --python "$venv_dir/bin/python" -r "$repo_dir/requirements-dev.txt"
    chmod -R a+rX "$UV_PYTHON_INSTALL_DIR"
elif command -v python3.15 >/dev/null; then
    python3.15 -m venv --clear "$venv_dir"
    "$venv_dir/bin/python" -m pip install -r "$repo_dir/requirements-dev.txt"
else
    cat >&2 <<'EOF'
Bootstrap requires uv or Python 3.15.
On Arch Linux, run as root:
  pacman -Syu --needed uv
Then run this bootstrap command again. uv will download Python 3.15.
EOF
    exit 1
fi
chmod -R a+rX "$venv_dir"
# Catch Python/Ansible import incompatibilities before running Galaxy.
if ! ANSIBLE_LOCAL_TEMP="$repo_dir/.ansible/tmp" "$venv_dir/bin/ansible-pull" --version; then
    echo "Bootstrap failed: $venv_dir/bin/ansible-pull cannot execute. Check its Python interpreter and the installation errors above." >&2
    exit 1
fi
ANSIBLE_LOCAL_TEMP="$repo_dir/.ansible/tmp" "$venv_dir/bin/ansible-galaxy" collection install \
    -r "$repo_dir/requirements.yml" -p "$runtime_dir/collections"
if [ "$prune_old_python" = true ]; then
    "$venv_dir/bin/python" "$repo_dir/scripts/prune-python.py" "$runtime_dir"
fi
echo "Environment ready: $runtime_dir (executables: $venv_dir/bin)"
