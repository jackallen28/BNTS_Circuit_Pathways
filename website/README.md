# Circuit Pathways: the showcase website

A fun, scroll-and-try website that shows off **PiPath** (Python on the Raspberry Pi) and
**ArduinoPath** (Arduino and ESP, in text or blocks).

**Open `index.html`** in Edge, Chrome, Firefox or Safari. It's plain files: no server, no
internet and no build step needed, so it works from this folder, a USB stick, a shared drive or
any web server. (Nothing is sent anywhere: no trackers, no fonts or scripts from the internet.)

## What's on it

- **Home:** the floating glass BNTS logo, "Where do you want to explore?", and what the two apps share.
- **PiPath** (`#pipath`) and **ArduinoPath** (`#arduinopath`): a scrolling story following Mia
  through one project each, mixing:
  - short silent clips from the apps (`media/snippets/`), some with numbered notes that pause the
    clip and highlight that part of the screen
  - two hands-on demos, the projects' simple test programs only:
    - **PiPath:** Check my wiring, then Traffic Lights step 1 (Run first, the Coach's clue,
      fill in the blank, the checklist, "I saw it happen", stars), with the help-level switch
    - **ArduinoPath:** the Wiring Wizard for the ultrasonic distance sensor (meet it, wire it,
      the forced test, then program it with the Serial Monitor)
  - small interactive bits: help levels, nudge cards, gradual release, text or blocks, boards
  - everything else listed as **Available in the Circuit Pathways release app**
  - the **full walkthrough videos** (with captions) at the bottom (`media/full/`)

## Files

```
index.html          the page (all three views)
css/site.css        the look: BNTS colours, Windows 95 bits for PiPath, Vista glass for ArduinoPath
js/site.js          views, scroll reveals, clips + notes, the two demos
js/data.js          activity / project / part / board lists, made from the two apps' own content
img/                the BNTS logo and pixel mark
media/snippets/     short silent clips (960×540) + poster frames
media/full/         the full walkthroughs: PiPath Traffic Lights (captions), ArduinoPath Smart Bin
                    (text with captions; blocks)
```

## Updating it

- **New walkthrough videos:** replace the files in `media/full/` (same names), then re-cut the
  snippets with ffmpeg from the clean versions, e.g.
  `ffmpeg -ss 57 -i clean.mp4 -t 8 -an -vf scale=960:540 -c:v libx264 -crf 27 -movflags +faststart media/snippets/pi-coach.mp4`
  plus a poster: `ffmpeg -ss 61.8 -i clean.mp4 -frames:v 1 -vf scale=960:540 media/snippets/pi-coach.jpg`.
  A note's highlight box (`data-notes` in `index.html`, in % of the frame) is measured on the
  poster frame (60 % of the way through the clip).
- **New activities:** regenerate `js/data.js` from PiPath's `data/catalog.toml` and ArduinoPath's
  `content/` (projects, tiers, parts, boards).
