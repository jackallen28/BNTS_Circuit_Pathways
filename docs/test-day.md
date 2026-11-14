# Test day: the school server, a student Pi, a laptop and an Arduino, end to end

This is the one page to follow. It takes you from a box of Pis to "everything works with real hardware" in about two
hours (most of it waiting for downloads). Then work down the [hardware checklist](hardware-checklist.md).

## What you need

- **The school server:** a Raspberry Pi 4 or 5 (4 GB or more), 64-bit Raspberry Pi OS, a network cable if you can, and
  the internet for the first set-up (the board tools are about 1.5 GB).
- **A student Pi:** a Pi 3, 4 or 5 with 64-bit Raspberry Pi OS **with the desktop**, a screen and keyboard, on the same
  network, and its breadboard wired to PiPath's standard pin plan (an LED on GPIO 17 with a 330Ω resistor is enough).
- **A laptop** with Chrome or Edge on the same network (a student account without admin rights is best).
- **Boards:** a genuine Arduino Uno, a Nano clone, a NodeMCU, an ESP32, and **USB cables that carry data** (some only
  charge: if no board ever appears, change the cable first). A class kit: LEDs, 220Ω and 330Ω resistors, a button, a
  buzzer, jumper wires, a breadboard.
- **The download:** `circuitpathways-pi-VERSION.tar.gz`. Get it from the repository's **Releases** (made by **Actions >
  Release**), or make it on any computer with Go 1.24: `bash tools/build-pi.sh` (it lands in `dist/`).
- Optional: a computer with Node 18+ to run the **preflight** (or run it on the server Pi: `sudo apt install nodejs`).

## 1. The school server (about 30 minutes, mostly downloading)

Copy the download to the server Pi (a USB stick is fine). In a Terminal there:

```bash
tar xzf circuitpathways-pi-*.tar.gz
```

```bash
cd circuitpathways-pi && sudo bash install-server.sh
```

At the end it prints the server's addresses, **the first teacher code**, and the student Pi command. Write them down.
If the board tools couldn't download, it says how to try again; everything else still works.

## 2. A laptop

1. Open **http://pathways.local** (or the address the installer printed). The home page loads. A note at the top says
   to use the secure address.
2. Open **http://pathways.local/trust**, download the certificate and follow the steps for your computer (no admin
   needed on Windows). Press **Check this computer**: it should say it's set up and open **https://pathways.local**.
3. **Teacher sign in** with the teacher code. In the teacher portal, make a class, and **set work**: *Blink & Traffic
   Lights* and PiPath's *Hello, Pi!*. Keep this tab open.

## 3. A student Pi (about 5 minutes)

On the student Pi, in a Terminal:

```bash
curl -fsSL http://pathways.local/install/student-pi.sh | sudo bash
```

**Circuit Pathways**, **PiPath** and **ArduinoPath** appear in the Pi menu (Education) and on the desktop.

## 4. The preflight

From the laptop (or any computer with Node 18+ on the network), with the repository:

```bash
node tools/preflight.mjs http://pathways.local --teacher-code "THE TEACHER CODE"
```

You want **Ready for the test day**. Then on the student Pi itself (where the server is `http://localhost:8080`):

```bash
node tools/preflight.mjs http://localhost:8080 --pi "$(pilink id)"
```

(No Node on the student Pi? Skip it: section 8 of the checklist does the same by hand.)

## 5. Work down the hardware checklist

[hardware-checklist.md](hardware-checklist.md) is the list of ticks: laptops and boards, the teacher portal, a student
Pi as a student's computer, and **offline** (unplug the server and keep working). Keep a note of anything odd with a photo;
the checklist ends with what to write down and quick fixes.

Every page shows which build you are on (the About box, and the foot of the home page): put it in your notes.

## Before the day: try it all on one computer (no Pi)

`bash tests/pi-server/smoke.sh` runs a school server with https and installs a student Pi from it into a test folder,
starts them, connects a pretend Pi Link, runs the preflight on both, and turns the server off to check the student Pi
copes. CI runs it on every change (and once with the real board tools, so a real compile goes through the school server
and through a student Pi).

## What has and hasn't been checked

Checked by automated tests on every change: the simulators and every project's model answer, a **real compile for every
board**, every Wiring Wizard test program, classes, set work and progress, a student Pi passing everything to the school
server over https and coping when it's gone, the student Pi installer (into a folder), the Pi relay with the real Pi app
on **pretend pins**, uploading to a **pretend board**, and the preflight. The school server installer was run in a test
container (without systemd).

**Not checked until you do this test:** the installers on real Pis (systemd, the `pathways.local` name, ports 80 and
443), laptops trusting the certificate (Windows, Mac, Chromebook), uploading to real Uno, Nano, NodeMCU and ESP32 boards
(the ESP uploader is the least tested), the Wiring Wizard's Test on real boards, Grove modules, a real Pi's pins and
camera, and how many laptops one server Pi handles at once. Treat the first run on each as the test.
