# Test day: a Raspberry Pi and an Arduino, end to end

This is the one page to follow. It takes you from nothing deployed to "everything works with real hardware".
Two ways, and you can do both:

- **A. Rehearsal on one laptop** (no accounts, about an hour, mostly downloading). Proves your boards, your cables and the
  Pi's pins work with the software, before anything is online.
- **B. The real thing** (Cloudflare, plus a compiler somewhere). Proves the school setup: the Pi beta site, classes, and a
  Pi that is not on your laptop's network.

Either way the last step is the same: run the **preflight**, then work down the **hardware checklist**.

## What you need on the day

- A laptop with **Chrome or Edge**, **Go 1.24** and **Node 18+** (only to run the commands below).
- **Boards** (the ones in your kit): a genuine Arduino Uno, a Nano clone, a NodeMCU, an ESP32. **USB cables that carry data**
  (some only charge: if no board ever appears, change the cable first).
- A **class kit**: LEDs, 220Ω and 330Ω resistors, a button, a buzzer, jumper wires, a breadboard. For Grove: the Base Shield
  (Arduino) and Base Hat (Pi) and a few modules.
- A **Raspberry Pi** (4 or 5, Raspberry Pi OS with the desktop) on the same WiFi, a keyboard and screen for it, and its
  breadboard wired to PiPath's standard pin plan (LED on GPIO 17 with a 330Ω resistor is enough to start).
- About an hour of internet for the compilers (1.5 GB, once).

## A. Rehearsal on one laptop

You run the site yourself on the laptop. There is nothing to sign up for.

**1. Get the compilers** (once; this is what Upload needs):

```bash
go run ./cmd/circuitpathways -setup -warm -tools ~/circuitpathways-tools
```

(On Windows give a full folder instead of `~/...`, for example `-tools C:\circuitpathways-tools`, here and in step 2.)

**2. Start the site** (leave it running; Windows PowerShell works the same):

```bash
go run ./cmd/circuitpathways -dev -tools ~/circuitpathways-tools
```

Open **http://localhost:8080** in Chrome or Edge. Sign in as a teacher with the code `teacher-code-dev` (it works in both
apps for 12 hours). `localhost` counts as a secure site, so Web Serial and Python both work.

**3. Check it:**

```bash
node tools/preflight.mjs http://localhost:8080 --teacher-code teacher-code-dev
```

Everything should be a tick, including **a real compile worked**. If not, the line says what to do.

**4. Arduino:** plug in a board and follow section 2 onward of the [hardware checklist](hardware-checklist.md)
(Uno first, then Nano, NodeMCU, ESP32). If Chrome's list is empty, press **Can't see your board?**.

**5. The Pi.** The Pi has to reach your laptop. Find the laptop's address on the WiFi (for example `192.168.1.20`), then make
the Pi its key and installer. On the laptop:

```bash
PI_KEY_SECRET=dev-pi-key-secret-do-not-use-in-production go run ./cmd/circuitpathways -pi-keys 1 -pi-out private/pi -server http://192.168.1.20:8080
```

(Windows PowerShell: `$env:PI_KEY_SECRET="dev-pi-key-secret-do-not-use-in-production"` first, then the same command without
the `PI_KEY_SECRET=` part.) That writes `private/pi/PI-KEYS.md` (the Pi's ID, such as `K7M2-QX9P`) and an installer
`install-pi-K7M2-QX9P.sh`. Copy the installer to the Pi (a USB stick is fine) and, in a Terminal on the Pi:

```bash
sudo bash install-pi-K7M2-QX9P.sh
```

Then, on the laptop:

```bash
node tools/preflight.mjs http://localhost:8080 --teacher-code teacher-code-dev --pi K7M2-QX9P --no-compile
```

and **PiPath > Free Play > Run on: My Raspberry Pi**: type the ID, press **Link**, run `from gpiozero import LED` /
`LED(17).blink()`. The real LED should blink, and **Stop** should turn it off.

> **What the rehearsal can't show:** the Pi's own menu shortcuts (Circuit Pathways, PiPath, ArduinoPath) open the site in the
> Pi's browser, and a browser only runs Python and Web Serial on a secure site (`https://` or `localhost`), not on
> `http://192.168...`. Test the Pi's shortcuts in part B.

## B. The real thing

You need a Cloudflare account (free) for the site, and somewhere to run the **compiler** (Upload to a board needs it; PiPath
and the simulators don't).

**1. The compiler.** Pick one:

- **Render, paid plan** (simplest): deploy `render.paid.yaml`. Set the same `COMPILE_KEY` (a long random text) on it. Its
  address is the `COMPILE_URL`. See [deploy-render.md](deploy-render.md).
- **Any always-on computer** with the compilers (`-setup -warm` as in A.1) running
  `COMPILE_KEY=... go run ./cmd/circuitpathways -tools ~/circuitpathways-tools`, reachable by a public address.

No compiler yet? Do everything else; the preflight will say Upload won't work, and the rest of the checklist still can.

**2. The Pi beta site on Cloudflare.** Follow [../cloudflare/README.md](../cloudflare/README.md), "Set it up (once)" and
"The Pi beta site": create the database, put its id in the `pi` section of `wrangler.jsonc`, set the secrets
(`CLASS_SECRET`, `TEACHER_CODES`, `PI_KEY_SECRET`, and `COMPILE_URL` and `COMPILE_KEY` if you have a compiler), then:

```bash
cd cloudflare && npm ci && npm run deploy:pi
```

(Or **Actions > Deploy to Cloudflare**, choosing `pi`.) It prints the site's address, such as
`https://circuit-pathways-pi.YOUR-NAME.workers.dev`.

**3. A key and installer for the Pi**, with the same `PI_KEY_SECRET` you gave the site, pointing at it:

```bash
PI_KEY_SECRET=your-real-secret go run ./cmd/circuitpathways -pi-keys 1 -pi-out private/pi -server https://circuit-pathways-pi.YOUR-NAME.workers.dev
```

Copy `install-pi-....sh` to the Pi and run it with `sudo bash` (as in A.5). The Pi menu then has **Circuit Pathways**,
**PiPath** and **ArduinoPath**, and they open the site already linked to that Pi.

**4. Preflight**, from any computer:

```bash
node tools/preflight.mjs https://circuit-pathways-pi.YOUR-NAME.workers.dev --expect pi-beta --pi K7M2-QX9P --teacher-code "a code you make up"
```

You want **Ready for the test day**. (On the Pi beta any code of 8 or more characters works as a teacher code. On the real
site use one of the school's `TEACHER_CODES`.)

## Then: work down the hardware checklist

[hardware-checklist.md](hardware-checklist.md) is the list of ticks. Do **section 8 (the Pi as a student computer)** on the
Pi itself, using its menu shortcuts, and everything else on the laptop. Keep a note of anything odd with a photo; the
checklist ends with what to write down and quick fixes.

Every page shows which build you are on (the About box, and the foot of the home page): put it in your notes, so a problem can
be matched to the exact version.

## What has and hasn't been checked

Checked by automated tests, every time the code changes: the simulators and every project's model answer, a **real compile
of every board** (arduino-cli), every Wiring Wizard test program, the saved classes, the Pi relay with the real Pi app on
**pretend pins**, uploading to a **pretend board**, and the preflight itself.

**Not checked until you do this test:** uploading to real Uno, Nano, NodeMCU and ESP32 boards (the ESP uploader is the least
tested), the Wiring Wizard's Test on real boards, Grove modules, a real Pi's pins and camera, the Pi's shortcuts and
low-memory mode on a small Pi, and Cloudflare itself (everything has been tried against Cloudflare's own runtime on a
computer, never on a real account). Treat the first run on each as the test.
