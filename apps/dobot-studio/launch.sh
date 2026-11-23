#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -m dobot_studio "$@"
fi
exec python3 -m dobot_studio "$@"
