#!/usr/bin/env bash
# Circuit Pathways: set up the SCHOOL SERVER (the main Raspberry Pi).
#
# Run this once on the Pi that will be the school server (a Pi 4 or 5 with 4 GB or more, 64-bit Raspberry Pi OS),
# from the folder you unpacked the download into:
#     sudo bash install-server.sh
#
# It installs Circuit Pathways as a service that starts with the Pi. Every computer on the school network then
# opens https://pathways.local (or the Pi's address): students for PiPath and ArduinoPath, teachers for their
# portal. Classes, the work teachers set, and students' first names, school and work are kept on this Pi only.
#
# Settings go after "sudo", for example:  sudo CP_SCHOOL="Eltham High School" bash install-server.sh
#   CP_HOSTNAME=pathways   this Pi's name on the network (it is then pathways.local). CP_HOSTNAME=keep leaves it.
#   CP_SCHOOL="..."        the school's name, filled in for new classes
#   CP_TOOLS=no            skip the board tools (1.5 GB download): the simulators work, uploading to boards doesn't
#   CP_TEACHER="Ms Lee"    a label for the first teacher code
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WANT_HOST="${CP_HOSTNAME:-pathways}"
SCHOOL="${CP_SCHOOL:-Banyule Nillumbik Tech School}"
TOOLS="${CP_TOOLS:-yes}"
FIRST="${CP_TEACHER:-First teacher}"
DATA=/var/lib/circuitpathways
TOOLDIR=/opt/circuitpathways

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nSorry: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" == 0 ]] || die "run this with sudo:  sudo bash install-server.sh"
case "$(uname -m)" in
  aarch64|arm64) BIN="$HERE/circuitpathways-linux-arm64" ;;
  x86_64) BIN="$HERE/circuitpathways-linux-amd64" ;;
  *) die "this Pi runs 32-bit Raspberry Pi OS. The school server needs 64-bit Raspberry Pi OS." ;;
esac
[[ -f "$BIN" ]] || die "$(basename "$BIN") isn't next to this script. Unpack the whole download first."
[[ "$SCHOOL" =~ ^[A-Za-z0-9\ .,\'\&\(\)/-]{1,60}$ ]] || die "CP_SCHOOL can only have letters, numbers and simple punctuation."

say "Installing Circuit Pathways"
install -d /usr/local/lib/circuitpathways /etc/circuitpathways
install -m 755 "$BIN" /usr/local/lib/circuitpathways/circuitpathways
ln -sf /usr/local/lib/circuitpathways/circuitpathways /usr/local/bin/circuitpathways
id circuitpathways >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin circuitpathways
install -d -m 700 -o circuitpathways -g circuitpathways "$DATA"
install -d -m 755 -o circuitpathways -g circuitpathways "$TOOLDIR"

if [[ "$WANT_HOST" != keep && "$(hostname)" != "$WANT_HOST" ]]; then
  [[ "$WANT_HOST" =~ ^[a-z][a-z0-9-]{0,30}$ ]] || die "CP_HOSTNAME must be lower-case letters, numbers and dashes."
  say "Naming this Pi \"$WANT_HOST\" (so it is $WANT_HOST.local on the network)"
  OLD="$(hostname)"
  hostnamectl set-hostname "$WANT_HOST" 2>/dev/null || echo "$WANT_HOST" > /etc/hostname
  if grep -q "^127.0.1.1" /etc/hosts; then sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$WANT_HOST/" /etc/hosts; else printf '127.0.1.1\t%s\n' "$WANT_HOST" >> /etc/hosts; fi
  systemctl restart avahi-daemon 2>/dev/null || true
  [[ "$OLD" != "$WANT_HOST" ]] && echo "(It was called \"$OLD\".)"
fi
command -v avahi-daemon >/dev/null || { apt-get install -y -qq avahi-daemon >/dev/null 2>&1 || echo "Note: avahi-daemon (for the .local name) isn't installed: use the Pi's address instead."; }

printf 'SCHOOL=%s\n' "$SCHOOL" > /etc/circuitpathways/server.conf

if [[ "$TOOLS" == yes ]]; then
  say "Installing the board tools for uploading to Arduino and ESP boards (about 1.5 GB, from the internet: 10 to 40 minutes)"
  if sudo -u circuitpathways /usr/local/bin/circuitpathways -setup -warm -tools "$TOOLDIR"; then
    echo "The board tools are ready."
  else
    printf '\nNote: the board tools could not be installed (is this Pi on the internet?).\nEverything else works. Try again later with:  sudo -u circuitpathways circuitpathways -setup -warm -tools %s\n' "$TOOLDIR"
  fi
fi

say "Making the server's own https certificate and the first teacher code"
CODES="$(sudo -u circuitpathways /usr/local/bin/circuitpathways teacher list -data "$DATA" 2>/dev/null | grep -c . || true)"
if [[ "${CODES:-0}" == 0 ]]; then
  CODE="$(sudo -u circuitpathways /usr/local/bin/circuitpathways teacher add -data "$DATA" "$FIRST")"
else
  CODE="(you already have teacher codes:  sudo circuitpathways teacher list)"
fi
sudo -u circuitpathways /usr/local/bin/circuitpathways certificate -data "$DATA" > /dev/null

cat > /etc/systemd/system/circuitpathways.service <<UNIT_END
[Unit]
Description=Circuit Pathways school server
After=network-online.target
Wants=network-online.target

[Service]
User=circuitpathways
EnvironmentFile=/etc/circuitpathways/server.conf
ExecStart=/usr/local/bin/circuitpathways -mode school -data $DATA -tools $TOOLDIR -http :80 -https :443
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=$DATA $TOOLDIR
PrivateTmp=true
MemoryMax=85%

[Install]
WantedBy=multi-user.target
UNIT_END
systemctl daemon-reload
systemctl enable --now circuitpathways
systemctl restart circuitpathways
sleep 2
systemctl is-active --quiet circuitpathways || die "the service didn't start. See:  journalctl -u circuitpathways -n 50"

NAME="$(hostname).local"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
FP="$(sudo -u circuitpathways /usr/local/bin/circuitpathways certificate -data "$DATA")"
cat <<DONE

=====================================================================
  The Circuit Pathways school server is running.

  Open it on any computer on the school network:
      https://$NAME      (or https://$IP)
  The first time, each computer needs to trust the server: open
      http://$NAME/trust
  and follow the steps there (or ask IT to do it for every laptop).

  Teacher code:  $CODE
  More codes:    sudo circuitpathways teacher add "Ms Lee"

  Set up each student Pi (once, with this server on):
      curl -fsSL http://$NAME/install/student-pi.sh | sudo bash

  The certificate's fingerprint (to check on a laptop):
      $FP
  Status: sudo circuitpathways status    Logs: journalctl -u circuitpathways
=====================================================================
DONE
