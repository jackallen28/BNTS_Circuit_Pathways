#!/bin/sh
# For the browser tests: builds the site and runs the Worker locally with a fresh database.
# Usage: serve.sh PORT [ENV]     (ENV "pi" runs the Pi beta: a class code is optional)
# Each run builds into its own folder, so two Workers can start at the same time.
set -e
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
persist="$(mktemp -d)"
(cd .. && go run ./cmd/circuitpathways -export "$persist/dist" >/dev/null)
envargs=""
[ -n "$2" ] && envargs="--env $2"
./node_modules/.bin/wrangler d1 migrations apply DB --local --persist-to "$persist" $envargs >/dev/null
exec ./node_modules/.bin/wrangler dev --local --port "$1" --persist-to "$persist" $envargs --assets "$persist/dist" --show-interactive-dev-session=false \
  --var CLASS_SECRET:e2e-class-secret-0123456789 --var TEACHER_CODES:teacher-code-dev,teacher-code-two \
  --var PI_KEY_SECRET:dev-pi-key-secret-do-not-use-in-production
