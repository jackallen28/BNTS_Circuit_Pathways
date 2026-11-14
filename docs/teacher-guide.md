# Circuit Pathways: teacher guide

Circuit Pathways teaches coding step by step, like a tutor sitting beside each student. It has two apps that run in the
student's browser: **PiPath** (Python on the Raspberry Pi) and **ArduinoPath** (Arduino and ESP boards, in blocks or
C++). Students choose their projects and how much help they get. There is no generative AI: every hint was written by
people.

## Which site are you on?

| Site | Class code | What it is for |
|---|---|---|
| **The real site** | Needed | Classes. A student joins with the class code you make. |
| **The Pi beta** | Optional | Students on Raspberry Pis. Without a code, work is saved on that Pi. With one, it is also saved to the class. |
| **The TEST version** | Optional | Trying it out. Nothing is kept on the computer; a student in a class has their work saved to the class. |

Ask whoever set it up which address to use. [`../README.md`](../README.md) explains the editions.

## Before your first lesson

1. **Sign in on the home page** with your teacher code. (On the Pi beta and TEST versions you can make up a code of your
   own, 8 or more characters. Write it down: your classes are kept under it, and it is how you get back to them.)
2. **Make a class** on the **Teacher page**: a name (no student names), the school, and the day it ends. You get a class
   code such as `ABCDE-FGHJK`. Give it to your students.
3. **Try it yourself first**, as a student, on one computer: join with the code, make a profile, open *Blink & Traffic
   Lights*, plug in a board and press **Upload**. (Uploading needs Chrome or Edge, a USB cable that carries data, and a
   site set up with a compiler.)
4. **If a school computer blocks something:** ask IT to allow the site's address, USB serial in Chrome or Edge, and,
   for clone boards on Windows, the CH340 / CP2102 USB drivers. Students can press **Can't see your board?** for tips.
5. **Check your kit.** The project picker says "needs a part not in your kit" using `content/arduinopath/kit.json`.
   To change it, edit that file.
6. **Run through the hardware checklist** ([hardware-checklist.md](hardware-checklist.md)) once with your boards and parts.

## How a lesson works

1. **Join.** On the home page a student types the class code, then their **first name(s)** and **school**. Students
   sharing a kit can add up to four names. No passwords. (On the Pi beta a student can skip the code and start straight
   away.)
2. **Help and board.** Beginner, Moderate or Advanced, and (in ArduinoPath) the board in their kit. Both can be changed
   in **Settings** at any time.
3. **The project picker.** Every project is open. Tiers (Getting Started, Sensors & Sound, Displays & Lights, Games,
   Challenge, WiFi & IoT, Grove) are only a guide. **Free Play** is always there for students' own ideas.
4. **ArduinoPath: the Wiring Wizard** opens first in each project: meet the parts, wire them one at a time with
   breadboard and schematic pictures, then **Test** each part before programming. Grove projects show which shield port
   each module plugs into.
5. **Programming, one step at a time.** Each step has instructions, starter code (sometimes with `___` blanks), and a
   checklist that ticks itself.
   - **Run** tries the code in the on-screen simulator. It needs no board.
   - **Watch the goal** shows what the step should do.
   - **Upload** (ArduinoPath) puts the code on the real board. **Run on: My Raspberry Pi** (PiPath) runs it on the
     student's own Pi.
   - **Check my code** only compiles.
   - The **Coach** explains every error ("clue") in plain English, with hints that start small.
6. **Stars** count independence (fewer hints is more stars), never speed.
7. **ESP boards:** the **Web page** button opens the Web Page Designer. Students drag buttons, switches, sliders, colour
   pickers, readings and status lights onto a phone, choose which part each one works, and press **Try it** to use the
   page on pretend parts before putting the code on the real board.

## The help levels

| Level | What students get |
|---|---|
| **Beginner** | Full explanations, every hint any time, and the first hint for each clue straight away. |
| **Moderate** | Each project's gradual release: guided steps first, then fewer hints, then brief goals. |
| **Advanced** (Years 9 and 10) | The goal first ("tutorial off"), real compiler messages with a technical note, fewer hints, steps can be skipped, **Jump to the challenge**, a code review after each step, and **Level up** challenges at the end. |

On top of the level, the Coach notices when a student seems **stuck** (the same clue twice, a checklist item that keeps
failing, lots of tries, or a quiet spell) and offers a hint, the goal or the full explanation. It also suggests a
harder level after a few steps done first try, or an easier one when a student is struggling. Students can switch
these nudges off in Settings.

## Seeing your class's work

On the **Teacher page**, open a class to see each student's first name(s), school, and what they have done. **See work**
shows their code. You can download everyone's work as a zip, or put it in a **class file** to keep on your computer.
You can change a class's end date, remove one student, or **Delete this class now**.

## What is kept, and for how long

- **A student with no class** keeps their work only on their own device (and in files they save).
- **A student in a class** has their first name(s), school and work kept with the class (on the Cloudflare site), so you
  can see it and they can carry on from any device. Nothing else about them is kept.
- **Everything is deleted** after the class's end date, or sooner if you delete the class or a student takes their name
  off it (**Take my name off the class** on the home page).
- The database provider keeps backups for a few weeks, so say so in your privacy notice. A sample is in
  [deploy-render.md](deploy-render.md), section 6.

## Curriculum

Every project links to the Victorian Curriculum Digital Technologies (Levels 7 to 10). Students and teachers see the
links in **Settings > Curriculum**.

## Safety

Every wiring screen reminds students:

- **Unplug the USB cable (or take the Pi's HAT off) before changing wires**, and put it back after.
- **Never connect 5V to an ESP board's or a Pi's pins.** ESP boards (NodeMCU, D1 mini, ESP32) and the Pi run on 3.3V.
  Projects with 5V parts add the right resistors automatically on those boards.
- **Always use a resistor with an LED.**

## Saving and moving work

- Code saves by itself about a second after typing stops, and progress saves at every step.
- **Settings > My work > Save my work** downloads a file of the student's own work, to keep or move to another computer
  (**Open my work**). A file made while in a class remembers the class, so opening it on another device links that device.
- **The WIPE page** (on the welcome screen of each app) is for the end of a program on a shared computer: **Save
  everyone's work**, then type **WIPE** to remove every profile in that browser.

## Troubleshooting

| What happens | What to do |
|---|---|
| No board in the browser's box | Use a USB cable that carries data (some only charge). Try another USB port. Press **Can't see your board?**. |
| Upload says the board isn't answering (Uno / Nano) | Pick the right board in Settings. Nano clones often need **Old bootloader** ticked. |
| Upload says "Failed to connect" (ESP boards) | Hold the board's **BOOT** / **FLASH** button while the upload starts. |
| Upload says another program is using the board | Close the Arduino IDE or any other Serial Monitor tab. |
| PiPath's Output stays empty | The school network may be blocking a file. The page says which, and to try another network (at the Tech School, **Tech Guest**). |
| A student can't join the class | Check the code and that the class hasn't ended. The code is not case sensitive. |
| Anything else | See the **When something goes wrong** list in [hardware-checklist.md](hardware-checklist.md). |
