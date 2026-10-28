# Circuit Pathways: the showcase website

A fun, scroll-and-try website that shows off **PiPath** (Python on the Raspberry Pi) and
**ArduinoPath** (Arduino and ESP, in text or blocks).

**Open `index.html`** in Edge, Chrome, Firefox or Safari. It's plain files: no server, no
internet and no build step needed, so it works from this folder, a USB stick, a shared drive or
any web server. (Nothing is sent anywhere: no trackers, no fonts or scripts from the internet.)

## What's on it

- **Home:** an overview: the spinning 3D BNTS logo (the pixel squares and the words), "Where do you want to explore?",
  what the two apps share, and then the **Program finder** (`#finder`).
- **Program finder** (`program-finder.html`, embedded at the end of the home page and linked from
  the other pages): seven questions about the class that recommend a program, a platform and a
  version, then **How we can tailor it** (coding style, help level, wiring support, simulator or
  real kit, with our pick for that class), and curriculum links. The tailoring options are data
  (`tailoring` in its `finder-config`). It also opens on its own.
- **Compare the Pair** (`#compare`): PiPath and ArduinoPath side by side, with the micro:bit beside
  them, a "What do your students want to do?" picker, and the micro:bit → ArduinoPath → PiPath pathway.
- **PiPath** (`#pipath`) and **ArduinoPath** (`#arduinopath`): a scrolling story following Mia
  through one project each, mixing:
  - short silent clips from the apps (`media/snippets/`), some with numbered notes that pause the
    clip and highlight that part of the screen
  - two hands-on demos, the projects' simple test programs only:
    - **PiPath:** Check my wiring, then Traffic Lights step 1 (Run first, the Coach's clue,
      fill in the blank, the checklist, "I saw it happen", stars), with the help-level switch
    - **ArduinoPath:** the Wiring Wizard for the ultrasonic distance sensor (meet it, wire it,
      the forced test, then program it with the Serial Monitor), drawn with the Fritzing parts
  - small interactive bits: help levels, nudge cards, gradual release, text or blocks, boards
  - the rest of each app's activities and projects (everything shown on the site and in the videos
    is in the release version)
  - ArduinoPath's blocks compared with MakeCode on the micro:bit
  - the boards ArduinoPath runs on (Fritzing pictures)
  - the **full walkthrough videos** at the bottom (`media/full/`), always with captions, next to
    the Smart Bin prototype animation (`media/extra/smartbin-loop.mp4`); ArduinoPath shows the text
    and blocks versions side by side, each with a picture of the app (`code-text.jpg`, `code-blocks.jpg`)

## Files

```
index.html          the page (all three views)
program-finder.html the program finder (self-contained; tells the page its height when embedded)
css/site.css        the look: BNTS colours, Windows 95 bits for PiPath, Vista glass for ArduinoPath
js/site.js          views, scroll reveals, clips + notes, the two demos
js/data.js          activity / project / part / board lists, made from the two apps' own content
img/                the BNTS logo and pixel mark
img/fritzing/       boards, breadboard and the HC-SR04 from the Fritzing parts library (CC BY-SA 3.0,
                    see LICENSE-fritzing.md), copied from ArduinoPath's ui/parts
media/extra/        the Smart Bin prototype animation (cropped, plays open then close)
media/snippets/     short silent clips (960×540) + poster frames
media/full/         the full walkthroughs, all with captions: PiPath Traffic Lights, ArduinoPath
                    Smart Bin in text and in blocks
```

## Updating it

- **New walkthrough videos:** replace the files in `media/full/` (same names, captioned versions only), then re-cut the
  snippets with ffmpeg from the clean versions, e.g.
  `ffmpeg -ss 57 -i clean.mp4 -t 8 -an -vf scale=960:540 -c:v libx264 -crf 27 -movflags +faststart media/snippets/pi-coach.mp4`
  plus a poster: `ffmpeg -ss 61.8 -i clean.mp4 -frames:v 1 -vf scale=960:540 media/snippets/pi-coach.jpg`.
  A note's highlight box (`data-notes` in `index.html`, in % of the frame) is measured on the
  poster frame (60 % of the way through the clip).
- **New activities:** regenerate `js/data.js` from PiPath's `data/catalog.toml` and ArduinoPath's
  `content/` (projects, tiers, parts, boards).
