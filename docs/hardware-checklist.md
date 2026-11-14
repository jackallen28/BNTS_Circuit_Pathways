# Real hardware test day

Do this before using a new release with a class. Automated tests already check the simulator, every project's model
answer, every Wiring Wizard test program, classes and set work, a student Pi with the school server, and the Pi relay.
They use **pretend** boards and a **pretend** Pi. This list checks what only real hardware can: the school server and
student Pis on a real network, laptops trusting the server, uploading over USB, the Serial Monitor, the Wiring Wizard's
Test, PiPath on a Pi's real pins, and working offline.

Set things up first with [test-day.md](test-day.md), and run its preflight, so you start from a server that is ready.
Allow about two hours. Tick each box. If something goes wrong, see **When something goes wrong** at the end.

## What you need

- The **school server** set up (`sudo bash install-server.sh`), and its teacher code.
- A **laptop** with Chrome or Edge on the school network (a student account without admin rights is best).
- A **student Pi** (64-bit Raspberry Pi OS with the desktop) set up from the school server, with a breadboard wired to
  PiPath's standard pin plan, and optionally a USB webcam.
- Boards: a **genuine Arduino Uno**, a **Nano clone (CH340 chip)**, a **NodeMCU** and an **ESP32 DevKit**, with
  **USB cables that carry data** (some only charge).
- A class kit: LEDs, 220Ω resistors, a button, a buzzer, jumper wires and a breadboard. For Grove: a Base Shield and
  the Grove modules.

## 1. Start (laptop)

- [ ] `http://pathways.local` opens in a couple of seconds, and says to use the secure address.
- [ ] `http://pathways.local/trust`: the steps for this computer work, and **Check this computer** says it's set up.
- [ ] `https://pathways.local` opens with no warning (the padlock).
- [ ] **Teacher sign in** with the teacher code: the teacher portal opens. Make a class. **Set work**: *Blink & Traffic
      Lights* (with a note) and PiPath's *Hello, Pi!*, and **Save**.
- [ ] In another browser (or a private window, set up with /trust too), join the class on the home page with the class
      code, a first name and the school. The home page shows the two pieces of work, with the note.
- [ ] Press **Blink & Traffic Lights**: ArduinoPath opens. Make a profile with the same first name, **Beginner** and
      **Arduino Uno R3**: the project opens by itself.

## 2. Genuine Uno: the main path

Plug in the Uno and wire three LEDs as the Wiring Wizard shows.

- [ ] Open **Blink & Traffic Lights**. The **Wiring Wizard** opens: the parts, then each wiring step with the
      breadboard picture and the safety reminder.
- [ ] On **Test it**, choose **On my real board**, press **Choose my board** and pick the Uno in the browser's box.
- [ ] Press **Test**. Each LED lights in turn: tick **I saw it work** for each, then **Start programming**.
- [ ] Fill in the blank and press **Run**: the on-screen LED blinks and the checklist ticks.
- [ ] Press **Upload**: "Uploading..." with a percentage, then **Uploaded ✓**. The real LED blinks.
- [ ] Delete a `;` and press **Check my code**: the Coach explains "A missing semicolon".
- [ ] Close the tab, open the site again and pick your name: the project opens on the same step, with your code.
- [ ] In the teacher portal, press **Refresh**: the progress table shows how many steps are done, and **See work**
      shows the code.

## 3. The Serial Monitor (Uno)

- [ ] **Serial Chatbot**: fill in step 1 and **Upload**. Your message appears in the **Serial Monitor**.
- [ ] Do step 3, **Upload**, type in the Serial Monitor's box and press **Enter**: the board answers "You said: ...".
- [ ] Change the speed list to another speed and back to 9600: it reconnects each time.
- [ ] Unplug the board while the Serial Monitor is open: it says the board was unplugged.

## 4. Nano clone (CH340)

- [ ] **Settings**: choose **Arduino Nano**. Upload Blink. If it says the board **isn't answering**, tick **Old bootloader
      (most Nano clones)** and upload again.
- [ ] The Wiring Wizard's **Test** works on the Nano too, with the same setting.
- [ ] Windows: if no board appears in the browser's box, press **Can't see your board?** and try **the USB way**. If it
      still isn't there, the laptop needs the **CH340 driver** (IT).

## 5. NodeMCU (ESP8266) and ESP32

- [ ] **Settings**: **NodeMCU**. Upload Blink. If it says **Failed to connect**, hold the **FLASH** button while the
      upload starts.
- [ ] Serial Chatbot step 1 on the NodeMCU: the message shows in the Serial Monitor.
- [ ] **Phone-controlled LED**: upload, join the board's WiFi on a phone, open the address the project shows, and the
      buttons turn the LED on and off.
- [ ] **ESP32 DevKit**: Upload Blink (hold **BOOT** if it says **Failed to connect**), then Serial Chatbot step 1.
- [ ] **Web page** button (ESP boards only): design a page, press **Put it in my code**, upload, and open it from a phone.

## 5b. The school's ESP boards (each with its own WiFi)

- [ ] Teacher portal (https), **3. ESP boards**: plug in a NodeMCU, press **Plug it in, then set it up**, pick the board.
      It compiles, uploads, and the table shows **✓** under Flashed. A phone sees the board's WiFi (`CP-ESP01-...`) and
      joins it with the password in the table; the page there shows the board's label.
- [ ] Set up an ESP32 the same way. **Print stickers** prints a sheet of labels and codes (no passwords).
- [ ] As a student in your class: **ArduinoPath > Settings > My ESP board**, type the NodeMCU's code: it shows the
      board's WiFi name and password.
- [ ] **Phone-controlled LED** on that NodeMCU: the code's `MY_WIFI_NAME` line has the board's WiFi; **Upload**, then
      the phone joins that WiFi and the buttons work.
- [ ] Plug in the ESP32 (another student's board) and press **Upload**: it stops with "This isn't your board", and the
      ESP32 keeps its program.
- [ ] A second student types the NodeMCU's code: it says someone else has that board.

## 6. Parts, with the Wiring Wizard's Test on a real board

- [ ] **Button Night Light**: pressing the real button ticks its row by itself.
- [ ] **Light Theremin** (LDR and buzzer): the LDR row shows a live bar that moves with the light; the buzzer beeps.
- [ ] **Servo Dial**: the servo sweeps; the pot's bar follows the knob.
- [ ] **Parking Sensor** on an ESP board: the wiring steps include the two 10kΩ resistors for the echo pin, and the
      distance reading changes with your hand.
- [ ] **Weather Station**: the OLED shows "Hello!" and the DHT row shows a temperature.
- [ ] A **Grove** project (for example **Grove: Light It Up**): the wizard shows which shield port each module goes in,
      and the module works on the real board.

## 7. Saving and classes

- [ ] A student with no class: work is still there after closing and reopening the browser.
- [ ] A student in a class: open the site on another laptop, join with the same code and name, and make a profile with
      the same name: their work comes across.
- [ ] **Settings > My work > Save my work** downloads a file; **Open my work** on another computer brings the work across.
- [ ] Teacher portal: **Download everyone's work**, **Change end date**, **Remove** a student, **Delete this class now**.
      A student can use **Take my name off the class**.
- [ ] On the server: `sudo circuitpathways status` shows the numbers, `sudo circuitpathways backup` makes a backup.

## 8. A student Pi as a student's computer

- [ ] **Circuit Pathways**, **PiPath** and **ArduinoPath** are in the Pi menu (Education), and **Circuit Pathways** is
      on the desktop. Double-click it: the app opens, with no "Execute?" question.
- [ ] Restart the Pi and double-click the icon straight away: it says it's starting, then opens.
- [ ] Updates: `journalctl -u circuitpathways-update -b` on the student Pi says it's up to date (or updated) from the
      school server. On the school server it says up to date, updated, or why not (no internet, or no token).
- [ ] Opening PiPath from the shortcut shows no ID to type. The home page names the Pi.
- [ ] Join the class from the Pi's home page (with a new first name): the set work shows, as on the laptop.
- [ ] In PiPath, **Run on: My Raspberry Pi** is already chosen. Wire an LED on GPIO 17 with a 330Ω resistor, run
      `from gpiozero import LED` / `LED(17).blink()`: the real LED blinks, and **Stop** turns it off.
- [ ] A program that prints shows its output in the Output box; typing an answer to `input()` works.
- [ ] PiPath opens noticeably faster the second time. Note how long the first open takes on this Pi.
- [ ] ArduinoPath on the Pi uploads to a board (compiled by the school server). If it says it can't use the USB port:
      `sudo usermod -aG dialout <username>`, then log out and in.
- [ ] Optional, a USB webcam: the camera activities (Photo Booth) work on **My Raspberry Pi**.

## 9. Offline (a student Pi without the school server)

- [ ] Unplug the school server's network cable (or switch it off). Within a minute, the student Pi's home page says the
      school server can't be reached.
- [ ] PiPath and ArduinoPath still open from the shortcuts. Do a step in each: it saves (close and reopen: still there).
      Run on My Raspberry Pi still works.
- [ ] Upload says it needs the school server (unless the Pi was set up with `CP_TOOLS=yes`). Joining a class says so too.
- [ ] Plug the server back in. Open the app again on the Pi: the work done offline appears in the teacher portal (Refresh).

## When something goes wrong

Write down three things and keep them with a photo of the screen:

1. **What you clicked**, and on which computer and board (for example "Pi 5, Nano clone, Upload in Blink step 2").
2. **What it said**: the message, the Coach's clue, or the **Output** tab under the Serial Monitor (select all, copy).
3. **Which computer and browser**, and the build line from the About box (for example "laptop, Edge 131, School server
   pathways.local, build 5e86a54").

Quick fixes to try first:

| What happens | Try this |
|---|---|
| No board in the browser's box | Another USB cable (some only charge), another USB port. Press **Can't see your board?** for tips and **the USB way**. |
| "The board isn't answering" (Uno / Nano) | Check the board in Settings. Nano clones: tick **Old bootloader**. |
| "Failed to connect" (ESP boards) | Hold **BOOT** / **FLASH** while the upload starts. |
| "Another program is using your board" | Close the Arduino IDE or any other Serial Monitor tab. |
| The Serial Monitor shows nothing | Check the speed matches `Serial.begin(...)`, and press the board's reset button. |
| `pathways.local` doesn't open | Use the server's address (`hostname -I` on the server Pi). Ask IT for a fixed address (a DHCP reservation). |
| The browser warns the connection isn't private | That laptop hasn't trusted the server yet: `http://pathways.local/trust`. |
| Upload or `input()` doesn't work on a laptop | You are on `http://`: use `https://pathways.local`. |
| **Run on my Pi** says the Pi is offline | `pilink status` and `pilink log` on the Pi. `sudo systemctl restart circuitpathways circuitpathways-pi`. |
| A student Pi says the school server can't be reached | Is the server on? On the student Pi: `journalctl -u circuitpathways -n 30`. |
| Anything on the server | `systemctl status circuitpathways` and `journalctl -u circuitpathways -n 50` on the server Pi. |
