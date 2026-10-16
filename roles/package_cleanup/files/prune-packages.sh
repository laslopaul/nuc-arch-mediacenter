#!/bin/bash
# Only remove explicitly nominated packages with no reverse dependencies.
set -euo pipefail
mode=$1
shift
protected=()
candidates=()
while (($#)); do
    case "$1" in
        --protect) protected+=("$2"); shift 2 ;;
        --candidate) candidates+=("$2"); shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[[ "$mode" == apply || "$mode" == check ]] || exit 2
# Query installed leaf packages once per pass. Query errors must not look absent.
while :; do
    installed=$(pacman -Qq)
    leaves=$(pacman -Qqt) || { rc=$?; [[ $rc == 1 && -z "$leaves" ]] || exit "$rc"; }
    progress=0
    for pkg in "${candidates[@]}"; do
        [[ "$pkg" =~ ^[a-zA-Z0-9@._+-]+$ ]] || exit 2
        skip=0
        for keep in "${protected[@]}"; do
            [[ "$pkg" != "$keep" ]] || skip=1
        done
        ((skip == 0)) || continue
        if [[ $'\n'"$installed"$'\n' == *$'\n'"$pkg"$'\n'* && $'\n'"$leaves"$'\n' == *$'\n'"$pkg"$'\n'* ]]; then
            if [[ "$mode" == check ]]; then
                echo "would remove $pkg"
            else
                pacman -R --noconfirm "$pkg"
                echo "removed $pkg"
                progress=1
            fi
        fi
    done
    [[ "$mode" == apply && "$progress" == 1 ]] || break
done
