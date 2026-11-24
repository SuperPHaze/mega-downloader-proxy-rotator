#!/bin/sh
# Finder starts .command files in Terminal, sometimes from the home directory.
set -eu
cd "$(dirname "$0")"
project_dir=$(pwd -P)
PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
export PATH

message() {
    case "${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}" in
        it*) printf '%s\n' "$2" >&2 ;;
        *)   printf '%s\n' "$1" >&2 ;;
    esac
}

supported() {
    "$1" -c 'import sys; sys.exit(not ((3, 11) <= sys.version_info[:2] <= (3, 14)))' 2>/dev/null
}

env_dir="$project_dir/venv"
if [ -d "$env_dir/Scripts" ] && [ ! -x "$env_dir/bin/python" ]; then
    env_dir="$project_dir/.venv-macos"
fi
python="$env_dir/bin/python"
if [ ! -x "$python" ]; then
    if [ -e "$env_dir" ]; then
        message "Incomplete Python environment at $env_dir. Move it aside and launch again." \
                "Ambiente Python incompleto in $env_dir. Spostalo e avvia di nuovo."
        exit 1
    fi
    for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && supported "$candidate"; then
            "$candidate" -m venv "$env_dir"
            break
        fi
    done
fi
if [ ! -x "$python" ] || ! supported "$python"; then
    message "This app requires Python 3.11–3.14. Check your installation and the local environment." \
            "Serve Python 3.11–3.14. Controlla l'installazione e l'ambiente locale."
    exit 1
fi
"$python" -m pip --disable-pip-version-check install --quiet -r "$project_dir/requirements.txt"
exec "$python" -m src.main
