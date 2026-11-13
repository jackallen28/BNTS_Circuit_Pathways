#!/bin/sh
# Makes dist/: the whole site, ArduinoPath's data and a _headers file, from the Go server's own copy.
# Needs Go. Pass --beta for the TEST version (adds noindex).
set -e
cd "$(dirname "$0")/.."
go run ./cmd/launch -export cloudflare/dist "$@"
