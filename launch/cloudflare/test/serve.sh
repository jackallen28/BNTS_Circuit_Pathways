#!/bin/sh
# For the browser tests: builds the site and runs the Worker locally with a fresh database.
# Usage: serve.sh PORT
set -e
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
sh build.sh >/dev/null
persist="$(mktemp -d)"
./node_modules/.bin/wrangler d1 migrations apply DB --local --persist-to "$persist" >/dev/null
exec ./node_modules/.bin/wrangler dev --local --port "$1" --persist-to "$persist" --show-interactive-dev-session=false \
  --var CLASS_SECRET:e2e-class-secret-0123456789 --var TEACHER_CODES:teacher-code-dev,teacher-code-two \
  --var PI_KEY_SECRET:dev-pi-key-secret-do-not-use-in-production
