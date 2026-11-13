# Real hardware test day

Do this before using a new release with a class. Automated tests already check the simulator, every project's model
answer, every Wiring Wizard test program, the saved classes and the Pi relay. They use **pretend** boards and a
**pretend** Pi. This list checks what only real hardware can: uploading over USB, the Serial Monitor, the Wiring
Wizard's Test, **Run on my Pi**, and the Raspberry Pi as a student computer.

Allow about two hours. Tick each box. If something goes wrong, see **When something goes wrong** at the end.

## What you need

- A laptop with **Chrome or Edge** (a student account without admin rights is best), and the site's address (the real
  site, the Pi beta or the TEST site).
- A **class code** from a teacher (or use the Pi beta, where a code is optional).
- Boards: a **genuine Arduino Uno**, a **Nano clone (CH340 chip)**, a **NodeMCU** and an **ESP32 DevKit**, with
  **USB cables that carry data** (some only charge).
- A class kit: LEDs, 220Ω resistors, a button, a buzzer, jumper wires and a breadboard. For Grove: a Base Shield and
  the Grove modules.
- A **Raspberry Pi** (4 or 5, Raspberry Pi OS with its desktop) with the Pi Link installer run on it (see
  [deploy-render.md](deploy-render.md), "Set up the Raspberry Pis"), a breadboard kit wired to PiPath's standard pin plan,
  and optionally a USB webcam.

## 1. Start (laptop)

- [ ] Open the site in Chrome or Edge. The home page loads in a couple of seconds.
- [ ] Join a class: type the class code, then your first name and school. The home page says you are in the class.
- [ ] Open **ArduinoPath**. Make a profile, choose **Beginner** and **Arduino Uno R3**.

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
      (On the Pi beta with no class, this is the same device. In a class it works from any device.)

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

- [ ] A student with no class (Pi beta): work is still there after closing and reopening the tab.
- [ ] A student who joins a class: the teacher sees their name and work on the **Teacher page** (**See work**).
- [ ] **Settings > My work > Save my work** downloads a file; **Open my work** on another computer brings the work across.
- [ ] The teacher can **Delete this class now**, and a student can use **Take my name off the class**.

## 8. Raspberry Pi as a student computer (Pi beta)

Run the Pi Link installer on the Pi first.

- [ ] **Circuit Pathways**, **PiPath** and **ArduinoPath** are in the Pi menu (Education) and on the desktop.
- [ ] Opening PiPath from the shortcut shows a window with no ID to type. The home page names the Pi.
- [ ] In PiPath, **Run on: My Raspberry Pi** is already chosen. Wire an LED on GPIO 17 with a 330Ω resistor, run
      `from gpiozero import LED` / `LED(17).blink()`: the real LED blinks, and **Stop** turns it off.
- [ ] A program that prints shows its output in the Output box; typing an answer to `input()` works.
- [ ] PiPath opens noticeably faster the second time (its large Python files are cached for a week), and moving between
      the picker and an activity feels quick. Note how long the first open takes on this Pi.
- [ ] On a Pi with 2 GB of memory or less, PiPath still runs (the launcher turns on Chromium's low-memory mode).
- [ ] ArduinoPath on the Pi uploads to a board. If it says it can't use the USB port:
      `sudo usermod -aG dialout <username>`, then log out and in.
- [ ] Optional, a USB webcam: the camera activities (Photo Booth) work on **My Raspberry Pi**.

## When something goes wrong

Write down three things and keep them with a photo of the screen:

1. **What you clicked**, and on which computer and board (for example "Pi 5, Nano clone, Upload in Blink step 2").
2. **What it said**: the message, the Coach's clue, or the **Output** tab under the Serial Monitor (select all, copy).
3. **Which site and browser** (for example "the Pi beta, Chrome 130").

Quick fixes to try first:

| What happens | Try this |
|---|---|
| No board in the browser's box | Another USB cable (some only charge), another USB port. Press **Can't see your board?** for tips and **the USB way**. |
| "The board isn't answering" (Uno / Nano) | Check the board in Settings. Nano clones: tick **Old bootloader**. |
| "Failed to connect" (ESP boards) | Hold **BOOT** / **FLASH** while the upload starts. |
| "Another program is using your board" | Close the Arduino IDE or any other Serial Monitor tab. |
| The Serial Monitor shows nothing | Check the speed matches `Serial.begin(...)`, and press the board's reset button. |
| PiPath's output box stays empty | The school network may block a file. The page names it and says to try another network (at the Tech School: **Tech Guest**). |
| **Run on my Pi** says the Pi is offline | Check the Pi is on and on the network. It can take a minute after it starts. `pilink status` on the Pi shows more. |
