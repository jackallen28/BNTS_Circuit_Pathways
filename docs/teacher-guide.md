# Circuit Pathways: teacher guide

Circuit Pathways teaches coding step by step, like a tutor sitting beside each student. It has two apps that run in the
student's browser: **PiPath** (Python on the Raspberry Pi) and **ArduinoPath** (Arduino and ESP boards, in blocks or
C++). Students choose their projects and how much help they get. There is no generative AI: every hint was written by
people.

## Where it runs

Circuit Pathways runs on your school's own Raspberry Pi (the **school server**). Nothing is on the internet.

| Where | Students open | What it is for |
|---|---|---|
| **A laptop** | `https://pathways.local` in Chrome or Edge | PiPath (Python on the on-screen Pi) and ArduinoPath (the simulator, and uploading to a board on USB). |
| **A student Pi** | **PiPath** or **ArduinoPath** in the Pi menu | The same, plus PiPath on the Pi's real pins. It works even when the network is down. |

Setting it up (once, by you or IT): [`server.md`](server.md).

## Before your first lesson

1. **Get a teacher code.** Whoever looks after the server makes one for you: `sudo circuitpathways teacher add "Your name"`.
   Keep it private: your classes are kept under it.
2. **Set up your laptop** once: open `http://pathways.local/trust` and follow the steps. Then use `https://pathways.local`.
3. **Sign in on the home page** with your teacher code: the **teacher portal** opens.
4. **Make a class**: a name (no student names), the school, and the day it ends. You get a class code such as
   `ABCDE-FGHJK`. Give it to your students.
5. **Set work** (optional): pick ArduinoPath projects and PiPath activities, in order, with a note such as "steps 1 to 3
   by Friday". Students see the list on the home page, with links. Nothing is locked: they can still pick anything.
6. **Try it yourself first**, as a student, on one computer: join with the code, make a profile, open *Blink & Traffic
   Lights*, plug in a board and press **Upload**. (Uploading needs Chrome or Edge, a USB cable that carries data, and the
   secure address.)
7. **If a school computer blocks something:** ask IT to set up every laptop to trust the server (`server.md`), allow
   USB serial in Chrome or Edge, and, for clone boards on Windows, the CH340 / CP2102 USB drivers. Students can press
   **Can't see your board?** for tips.
8. **Check your kit.** The project picker says "needs a part not in your kit" using `content/arduinopath/kit.json`.
9. **Run through the hardware checklist** ([hardware-checklist.md](hardware-checklist.md)) once with your boards and Pis.

## How a lesson works

1. **Join.** On the home page a student types the class code, then their **first name(s)** and **school**. Students
   sharing a kit can add up to four names. No passwords. A class code is optional: without one, work is saved on that
   computer only. The home page then shows the **work you set**.
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
   - **Upload** (ArduinoPath) puts the code on the real board. On a student Pi, **Run on: My Raspberry Pi** (PiPath) runs
     it on that Pi's pins.
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

## The school's ESP boards

Set up each ESP board once in the teacher portal (**3. ESP boards**): plug it into your laptop and press **Plug it in,
then set it up**. It gets a label, **its own WiFi name and password**, and a code: **Print stickers** and stick them on.
Students type the code in **ArduinoPath > Settings > My ESP board**. Their WiFi projects then use that board's own
WiFi (so only they can join it), and **Upload only works with their own board**. When a student leaves, their board is
free again; **Free it** does it by hand. Details: [`server.md`](server.md).

## Seeing your class's work

In the **teacher portal**, open a class:

- **Progress** on the work you set: **✓** finished, a number such as **3/7** for steps done, **·** opened, blank not
  started. Press **Refresh** for the latest.
- The **students**: first name(s), school, when they joined and last saved, and **See work** for their code.
- **Download everyone's work** (a zip of save files and code), or put it in a **class file** to keep on your computer.
- Change the class's end date, **Remove** one student, or **Delete this class now**.

Work saves to the class a moment after a student types. On a student Pi with no network, it waits and goes up when the
Pi can reach the school server again.

## What is kept, and for how long

- **A student with no class** keeps their work only in the browser on that computer (and in files they save).
- **A student in a class** has their first name(s), school and work kept with the class **on the school server**, so you
  can see it and they can carry on from any computer at school. Nothing else about them is kept, and nothing goes to the
  internet.
- **Everything is deleted** after the class's end date, or sooner if you delete the class or a student takes their name
  off it (**Take my name off the class** on the home page).
- Backups are only made when someone runs `sudo circuitpathways backup` on the server; say so in your privacy notice.

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
| PiPath's Output stays empty | Reload the page. If it still doesn't work, check the computer is using the school server's address (the server may need restarting: `sudo systemctl restart circuitpathways`). |
| The browser says the connection isn't private | That computer needs setting up once: `http://pathways.local/trust`. |
| Upload or Python's `input()` doesn't work on a laptop | Use the secure address, `https://pathways.local`. |
| `pathways.local` doesn't open | Use the server's address instead (ask whoever set it up), and check the computer is on the school network. |
| A student Pi says the school server can't be reached | Students can keep working; it is saved on the Pi and goes to the class later. Check the server Pi is on. |
| A student can't join the class | Check the code and that the class hasn't ended. The code is not case sensitive. |
| Anything else | See the **When something goes wrong** list in [hardware-checklist.md](hardware-checklist.md). |
