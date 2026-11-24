#!/bin/sh
# Add the Dobot Studio icon to the desktop and the applications menu.
# Run  sh install-desktop.sh --remove  to take it away again.
set -eu
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -m dobot_studio.desktop "$@"
fi
exec python3 -m dobot_studio.desktop "$@"
