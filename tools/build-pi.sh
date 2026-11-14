#!/usr/bin/env bash
# Builds the Circuit Pathways download for Raspberry Pi: one program (64-bit Raspberry Pi OS) and the school
# server's installer, in dist/circuitpathways-pi-VERSION.tar.gz. Run it on any computer with Go 1.24:
#
#     bash tools/build-pi.sh            # arm64 only (every Pi 3, 4, 5 and Zero 2 W on 64-bit Raspberry Pi OS)
#     ARCHES="arm64 amd64" bash tools/build-pi.sh   # also a PC version (for trying the school server on a PC)
#
# Copy the .tar.gz to the school server Pi (a USB stick is fine), then on the Pi:
#     tar xzf circuitpathways-pi-*.tar.gz && cd circuitpathways-pi && sudo bash install-server.sh
# Student Pis get the program from the school server itself (curl ... /install/student-pi.sh | sudo bash).
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="$(tr -d '[:space:]' < VERSION)"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo "")"
ARCHES="${ARCHES:-arm64}"
OUT="dist/circuitpathways-pi"
rm -rf "$OUT" && mkdir -p "$OUT"
for arch in $ARCHES; do
  echo "Building linux/$arch..."
  CGO_ENABLED=0 GOOS=linux GOARCH="$arch" go build -trimpath -ldflags "-s -w -X main.Version=$VERSION -X main.Commit=$COMMIT" \
    -o "$OUT/circuitpathways-linux-$arch" ./cmd/circuitpathways
done
cp internal/setup/install-server.sh "$OUT/install-server.sh"
cat > "$OUT/README.txt" <<README_END
Circuit Pathways $VERSION${COMMIT:+ (build $COMMIT)}: the school server for Raspberry Pi

1. On the Pi that will be the school server (a Pi 4 or 5, 4 GB or more, 64-bit Raspberry Pi OS,
   on the school network, and on the internet for the first set-up), open a Terminal here and run:

       sudo bash install-server.sh

   It names the Pi "pathways" (so it is pathways.local), installs the board tools for uploading
   (about 1.5 GB, from the internet), starts Circuit Pathways, and prints the first teacher code.

2. On each laptop: open http://pathways.local/trust once and follow the steps, then use
   https://pathways.local

3. On each student Pi (64-bit Raspberry Pi OS, same network):

       curl -fsSL http://pathways.local/install/student-pi.sh | sudo bash

Full guide: docs/server.md in the Circuit Pathways repository.
README_END
tar -C dist -czf "dist/circuitpathways-pi-$VERSION.tar.gz" circuitpathways-pi
ls -la "dist/circuitpathways-pi-$VERSION.tar.gz" "$OUT"
