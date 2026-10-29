# Pi Link (prototype): control a Raspberry Pi's pins from the browser

A student runs one small program on their Pi. Their browser, on the Circuit Pathways site, then
switches the Pi's GPIO pins on and off, fades LEDs, and reads buttons and sensors.

```
 Pi (circuitpathways_pi.py) ──outgoing──▶  Circuit Pathways site  ◀──outgoing── student's browser
        pins ◀─ commands ──────────────── (relay, in memory) ◀───── clicks, sliders
        pins ── pin states ─────────────▶                  ──────▶ the 40-pin header, live
```

**Why a relay?** Both sides only make *outgoing* connections to the site. That works when school
WiFi stops laptops from reaching other devices, and it avoids the browser rule that stops an
`https://` page talking to `http://192.168...` on the local network. No router settings, no IP
addresses, no certificates on the Pi.

## Try it (no Pi needed)

```
go run ./cmd/launch -dev
# in another terminal:
python3 site/pipath/remote/circuitpathways_pi.py --mock --server http://localhost:8080
```

It prints a code such as `K7M-2QX`. On the home page join a class (or sign in as a teacher:
`teacher-code-dev`), open **PiPath > Pi Link prototype**, and type the code. In `--mock` mode,
type `set 4 1` or `set 4 0` in the Pi app's terminal to press a pretend button on pin 4.

## On a real Pi

```
curl -O https://YOUR-SITE/pipath/remote/circuitpathways_pi.py
python3 circuitpathways_pi.py
```

The site hands out the file with its own address already filled in. It needs only Python 3 and
`gpiozero`, which are already on Raspberry Pi OS. (To start it automatically at boot, a
`systemd` service can run the same command.)

## What it can and can't do

| | |
|---|---|
| Pins | GPIO 2 to 27 only, as output, PWM, or input (floating, pull-up, pull-down) |
| Commands | `mode`, `write`, `pwm`, `release`, `all_off`, `read`, `ping`. Nothing else: no programs, no shell, no files |
| Checked twice | The site checks every command, and the Pi app checks it again |
| Fail-safe | If the Pi loses the site for 10 seconds, every output goes off. `Ctrl+C` lets every pin go |
| Speed | A command takes roughly the round trip to the site (tens to a couple of hundred ms) |
| Not for | Timing-critical things (servos need PWM hardware timing, ultrasonic echo timing, NeoPixels). Those stay in the simulator or in programs that run on the Pi itself |

## Privacy and safety

- The site passes only pin commands and pin states. It keeps them in memory while the Pi is
  connected and stores nothing. The Pi's label is a plain "Raspberry Pi" (never its host name,
  which might contain a student's name).
- A browser needs a **class code** (or teacher sign-in) to connect, and the Pi's **pairing code**
  (30 random bits, forgotten after the Pi disconnects). Pairing codes can't be guessed quickly:
  attempts are rate limited. Anyone who sees a code on a neighbour's screen *and* has a class code
  could connect, so teachers should treat a Pi's code like a seat number: it only matters
  for that session. One browser controls a Pi at a time; a newer one takes over.
- Wiring safety is the same as PiPath: HAT off before changing wires, a 330Ω resistor with every
  LED, never 5V on a GPIO pin. The page shows these.

## Next steps (not built yet)

1. **PiPath "Real Pi" mode in the browser:** run the student's `gpiozero` program in the simulator
   and mirror its pin changes to the real Pi through `pi-remote.js` (the `PiRemote` class).
2. **A start-at-boot installer** (`install.sh` that adds a `systemd` service) and an SD-card image.
3. **Camera and sensors:** stream readings from sensors the Pi can read well (DHT, distance).
4. **A teacher view** of which Pis are online in a class (needs a class code to be tied to a Pi).
5. **Direct mode** on the school network as an alternative when the internet is blocked: the Pi
   serves the page itself, over its own WiFi hotspot.
