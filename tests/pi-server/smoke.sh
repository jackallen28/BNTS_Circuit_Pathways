#!/usr/bin/env bash
# The school server and a student Pi, for real, on this computer (no root, no systemd, no Pi needed):
#   1. the school server starts with https (its own certificate), and a teacher code
#   2. a student Pi is installed from the school server's own installer, into a test folder
#   3. the student Pi starts, reaches the school server over https (trusting only its certificate), and its Pi
#      Link (the real Pi app, pretend pins) connects
#   4. the preflight passes on both (apart from the board tools, unless TOOLS is set)
#   5. the school server goes away: the student Pi says it is offline but keeps serving the site
#
#   bash tests/pi-server/smoke.sh [path/to/circuitpathways]      (builds one if not given)
set -euo pipefail
cd "$(dirname "$0")/../.."
WORK="$(mktemp -d)"
PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; rm -rf "$WORK"; }
trap cleanup EXIT
BIN="${1:-}"
if [[ -z "$BIN" ]]; then BIN="$WORK/circuitpathways"; go build -o "$BIN" ./cmd/circuitpathways; fi
HTTP=18380; HTTPS=18443; PIPORT=18390
step() { printf '\n== %s\n' "$*"; }
wait_for() { for _ in $(seq 1 60); do curl -fsS "$@" >/dev/null 2>&1 && return 0; sleep 0.5; done; echo "timed out waiting for $*" >&2; return 1; }

step "1. the school server"
CODE="$("$BIN" teacher add -data "$WORK/school" "Smoke test")"
"$BIN" -mode school -data "$WORK/school" -tools "${TOOLS:-$WORK/no-tools}" -http "127.0.0.1:$HTTP" -https "127.0.0.1:$HTTPS" > "$WORK/school.log" 2>&1 &
PIDS+=($!)
wait_for "http://localhost:$HTTP/healthz"
curl -fsS "http://localhost:$HTTP/ca.crt" -o "$WORK/ca.crt"
curl -fsS --cacert "$WORK/ca.crt" "https://localhost:$HTTPS/api/info" | grep -q '"edition":"school"'
echo "https works with the server's own certificate"
if curl -fsS "https://localhost:$HTTPS/healthz" >/dev/null 2>&1; then echo "https worked WITHOUT trusting the certificate" >&2; exit 1; fi

step "2. install a student Pi from the school server"
curl -fsS "http://localhost:$HTTP/install/student-pi.sh" -o "$WORK/student-pi.sh"
mkdir -p "$WORK/root"
case "$(uname -m)" in x86_64) M=x86_64 ;; *) M=aarch64 ;; esac
CP_PREFIX="$WORK/root" CP_MACHINE="$M" CP_NAME="Smoke Pi" bash "$WORK/student-pi.sh" > "$WORK/install.log" 2>&1 || { cat "$WORK/install.log"; exit 1; }
for f in usr/local/lib/circuitpathways/circuitpathways etc/circuitpathways/school-ca.crt etc/systemd/system/circuitpathways.service \
         etc/circuitpathways-pi.conf opt/circuitpathways-pi/circuitpathways_pi.py usr/local/bin/circuitpathways usr/local/bin/pilink; do
  [[ -e "$WORK/root/$f" ]] || { echo "the installer didn't make $f" >&2; cat "$WORK/install.log"; exit 1; }
done
grep -q "^SERVER=http://localhost:8080$" "$WORK/root/etc/circuitpathways-pi.conf"
grep -q -- "-mode student-pi" "$WORK/root/etc/systemd/system/circuitpathways.service"
echo "installed: the program, the certificate, the service, Pi Link and the shortcuts"

step "3. the student Pi starts and reaches the school server; its Pi Link connects"
SCHOOL="$(sed -n 's/^SCHOOL="\(.*\)"$/\1/p' "$WORK/student-pi.sh")"
"$WORK/root/usr/local/lib/circuitpathways/circuitpathways" -mode student-pi -addr "127.0.0.1:$PIPORT" -school "$SCHOOL" \
  -school-ca "$WORK/root/etc/circuitpathways/school-ca.crt" -data "$WORK/root/var/lib/circuitpathways" > "$WORK/pi.log" 2>&1 &
PIDS+=($!)
wait_for "http://localhost:$PIPORT/healthz"
for _ in $(seq 1 20); do curl -fsS "http://localhost:$PIPORT/api/info" | grep -q '"online":true' && break; sleep 0.5; done
curl -fsS "http://localhost:$PIPORT/api/info" | grep -q '"online":true' || { echo "the student Pi can't reach the school server"; cat "$WORK/pi.log"; exit 1; }
KEY="$(sed -n 's/^KEY=//p' "$WORK/root/etc/circuitpathways-pi.conf")"
ID="$(cat "$WORK/root/etc/circuitpathways-pi.id")"
RUNAS=(); [[ "$(id -u)" == 0 ]] && RUNAS=(--run-user nobody)
python3 -u "$WORK/root/opt/circuitpathways-pi/circuitpathways_pi.py" --mock --key "$KEY" --server "http://localhost:$PIPORT" --run-dir "$WORK/run" "${RUNAS[@]}" > "$WORK/piapp.log" 2>&1 &
PIDS+=($!)
sleep 3

step "4. the preflight on both"
NOCOMPILE=(--no-compile); [[ -n "${TOOLS:-}" ]] && NOCOMPILE=()
NODE_EXTRA_CA_CERTS="$WORK/ca.crt" node tools/preflight.mjs "https://localhost:$HTTPS" --expect school --teacher-code "$CODE" "${NOCOMPILE[@]}" | tee "$WORK/pre1.txt" || true
node tools/preflight.mjs "http://localhost:$PIPORT" --expect student-pi --teacher-code "$CODE" --pi "$ID" "${NOCOMPILE[@]}" | tee "$WORK/pre2.txt" || true
for f in pre1 pre2; do
  if grep "✗" "$WORK/$f.txt" | grep -v "no compiler" | grep -q .; then echo "the preflight found problems ($f)" >&2; exit 1; fi
done
grep -q "Pi Link is connected" "$WORK/pre2.txt"

step "5. the school server goes away"
kill "${PIDS[0]}"
for _ in $(seq 1 60); do curl -fsS "http://localhost:$PIPORT/api/info" | grep -q '"online":false' && break; sleep 1; done
curl -fsS "http://localhost:$PIPORT/api/info" | grep -q '"online":false' || { echo "the student Pi didn't notice the school server went away"; exit 1; }
curl -fsS "http://localhost:$PIPORT/pipath/" | grep -q "<title>PiPath"
OFF="$(curl -sS -X POST -H 'X-Circuit-Pathways: 1' -H 'Content-Type: application/json' "http://localhost:$PIPORT/api/class/join" -d '{"code":"ABCDE-FGHJK"}')"
echo "$OFF" | grep -q '"error":"offline"'
echo "offline: the site still works on the Pi, and it says the school server can't be reached"
printf '\nAll good: the school server and a student Pi work together, and apart.\n'
