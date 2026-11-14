# Pi Link: PiPath on a student Pi's real pins

Each **student Pi** runs Circuit Pathways itself (`-mode student-pi` on `http://localhost:8080`) and a small app, Pi
Link (`site/pipath/remote/circuitpathways_pi.py`). PiPath in that Pi's browser then runs students' programs on the Pi's
real pins, and the Pi Link page switches pins by hand.

```
 Pi Link app (circuitpathways_pi.py) ──▶  Circuit Pathways on the same Pi (relay)  ◀── the Pi's own browser
        pins ◀─ commands, programs ─────── (in memory, localhost:8080) ◀──────────── PiPath, Pi Link page
        pins ── pin states, output ───────▶                           ──────────▶ the 40-pin header, Output
```

Everything stays on the Pi, so it works with no network. Both the browser and the Pi app connect to the Pi's own
server; nothing listens on the network for Pi Link.

## Set it up

The student Pi installer does it all (see `docs/server.md`):

```bash
curl -fsSL http://pathways.local/install/student-pi.sh | sudo bash
```

It makes the Pi's own key (`circuitpathways pi-key`, kept in `/var/lib/circuitpathways`), installs Pi Link as a service
that starts at boot, the `pilink` helper, and the Pi menu and desktop shortcuts, which open the site with this Pi's ID.

## Try it (no Pi needed)

```bash
go run ./cmd/circuitpathways -dev
```

and in another terminal, with a key made with the dev secret (`tests/e2e/pi-key.js` shows how):

```bash
python3 site/pipath/remote/circuitpathways_pi.py --mock --key CPK1-... --server http://localhost:8080
```

It prints the Pi's ID. Open PiPath, choose **Run on: My Raspberry Pi** and type it. In `--mock` mode, type `set 4 1` or
`set 4 0` in the Pi app's terminal to press a pretend button on pin 4.

## What it can and can't do

| | |
|---|---|
| Pins | GPIO 2 to 27 only, as output, PWM, or input (floating, pull-up, pull-down) |
| Pin commands | `mode`, `write`, `pwm`, `release`, `all_off`, `read`, `ping` |
| Program commands | `run`, `stdin`, `stop`: run the student's own Python file (see "Running students' programs" below). No shell, no arbitrary files |
| Checked twice | The site checks every command, and the Pi app checks it again |
| Fail-safe | If the Pi loses the site for 10 seconds, every output goes off. `Ctrl+C` lets every pin go |
| Speed | A command takes a few milliseconds (it never leaves the Pi) |
| Not for | Timing-critical things (servos need PWM hardware timing, ultrasonic echo timing, NeoPixels). Those stay in the simulator or in programs that run on the Pi itself |

## Privacy and safety (pins)

- The Pi's own server passes only pin commands and pin states, in memory. Nothing is stored. The Pi's label is a plain
  "Raspberry Pi" or the `CP_NAME` it was installed with (never a student's name).
- Only this Pi's own browser can reach its server (it listens on `127.0.0.1`). One browser controls the Pi at a time; a
  newer one takes over.
- Wiring safety is the same as PiPath: unplug (or take the HAT off) before changing wires, a 330Ω resistor with every
  LED, never 5V on a GPIO pin. The page shows these.

## Running students' programs (PiPath: Run on: My Raspberry Pi)

The PiPath page sends the student's program (a `.py` file up to 40 KB, plus the lesson's small data files and, if the
program imports them, PiPath's `pipath_camera` / `pipath_computer` helpers, which the Pi fetches from the site
itself) to Pi Link. The Pi runs it with real Python and `gpiozero`, and streams what it prints back.

- One program at a time, in a temporary folder that is deleted afterwards, with a clean environment.
- As root (the installer's service) it **never** runs a program as root: it needs `RUN_USER` (the installer makes
  `cprun`) and drops to that user with its groups (gpio, video, i2c, spi). Not root: it runs as itself.
- Limits (`RLIMIT_*`): 10 minutes, 2 GB memory, 10 MB files, 64 processes; 200 000 characters of output. Stop = Ctrl+C,
  then SIGTERM, then SIGKILL. A page that stops answering for 25 s, or a lost connection for 10 s, stops the program.
- While it runs it owns the pins (the Pi lets go of any it held; pin commands are refused until it ends).
- The Pi sends back each chunk of output (merged so a chatty program can't fall behind), then the exit code and the
  names (and, for small text files, the contents) of files the program made, so the lesson's file checks work.
  Tracebacks show `File "program.py"`, not the temporary folder.
- Off switch: `RUN=no` in `/etc/circuitpathways-pi.conf` or `sudo pilink run off`; `--no-run` by hand.

Tests: `python3 -m unittest discover raspberry-pi` runs real programs (as `nobody` too, when run as root);
`tests/e2e/pipath-remote.spec.js` runs the real site, the real Pi app and a real browser together.

## Next steps (not built yet)

1. **Pin events from the program** (so a "pins" panel could show what the program is driving).
2. **An SD-card image** of a ready student Pi.
3. **Camera and sensors:** stream readings from sensors the Pi can read well (DHT, distance).
4. **A teacher view** of which student Pis are on, in the teacher portal.
