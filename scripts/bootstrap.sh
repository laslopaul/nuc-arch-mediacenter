#!/bin/bash
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
venv_dir=${1:-"$repo_dir/.venv"}
# uv supplies the same Python version on Arch and CI.
if command -v uv >/dev/null; then
    uv venv --python 3.13 --allow-existing "$venv_dir"
    uv pip install --python "$venv_dir/bin/python" -r "$repo_dir/requirements-dev.txt"
else
    python3.13 -m venv "$venv_dir"
    "$venv_dir/bin/python" -m pip install -r "$repo_dir/requirements-dev.txt"
fi
ANSIBLE_LOCAL_TEMP="$repo_dir/.ansible/tmp" "$venv_dir/bin/ansible-galaxy" collection install     -r "$repo_dir/requirements.yml" -p "$venv_dir/collections"
echo "Environment ready: $venv_dir"
