# Dobot Studio

A standalone Raspberry Pi 5 desktop app for the USB-connected Dobot Magician. A USB
webcam supplies hand gestures or body poses. The app processes frames in memory on
the Pi and talks directly to the arm over USB serial. It runs in a native Tk window,
with the teal, purple and glass styling of CircuitPath.

## Try the demo

From the extracted folder on a desktop with Python 3 and Tk installed, run:

```sh
./launch.sh
```

On a system that does not preserve executable permissions, use `sh launch.sh`.
Select **Enable controls**, then click **Thumb up** or **Victory sign** to move the
simulated arm to A or B. Try **Stop** or Escape. Change the tracking input to
**Body poses** to try that mapping. Demo mode starts by default and requires
neither a model nor a device.

## Install on Raspberry Pi 5

Use **64-bit Raspberry Pi OS with desktop**, a monitor or touchscreen, a USB
webcam, and an original Dobot Magician with its power supply and USB data cable.
Initial dependency and model downloads need internet access. Once installed, the app
works offline.

```sh
sudo apt update
sudo apt install -y python3-venv python3-tk curl libgl1 libegl1 libgles2 libportaudio2
sh setup-pi.sh
sh launch.sh
```

If serial connection fails with **Permission denied**, check the group on the USB
serial device with `ls -l /dev/ttyUSB*`. On Raspberry Pi OS that group is usually
`dialout`. If needed, run `sudo usermod -aG dialout "$USER"`, then sign out and
back in. Launch the app as your desktop user. Close other programs using the arm's
serial port. CP210x and CH340 adapters are typically handled by the OS.

## First hardware run

1. Keep the arm's workspace clear and have a physical way to stop it within reach.
   Power the Dobot with its own adapter. Plug its USB data cable and the webcam
   into the Pi.
2. In **USB hardware**, scan and select the arm's port. You can also type a stable
   path from `/dev/serial/by-id/` if one is available. Click **Connect**, then
   **Home**. Homing moves the arm.
3. With controls disarmed, use the Magician's hand-guiding button to position the
   tool. Release the button and let the arm settle, then click **Teach** for A.
   Repeat for B, and leave the tool at A or B. This prototype limits the two
   positions to 100 mm and 25° apart. Pick a short, clear straight path. Presets
   are held for the connected and homed session.
4. Choose **Hand gestures** or **Body poses**. Start the camera (index `0` by
   default, or enter a Linux path such as `/dev/video2`). Show one hand or
   one person clearly, then click **Enable controls**. Show a neutral input before
   each new motion gesture. Motion gestures must hold for about 350 ms.

| Action | Hand gestures | Body poses |
| --- | --- | --- |
| Position A | Thumb up | Raise your left wrist above your shoulder |
| Position B | Victory sign | Raise your right wrist above your shoulder |
| Stop and disarm | Closed fist | Raise both wrists |
| Neutral | Relaxed or open hand in view | Both wrists below shoulder height |

**Stop** and **Escape** disarm control. If motion is active, the app requests a
controller force-stop and clears pending commands. Tracking loss also disarms
control. An interrupted USB move requires homing and teaching again. If the USB
connection fails or the arm keeps moving, use the physical stop. Test
homing, short moves and stopping on the bench before using the app around others.

If the webcam opens with a blank or frozen view, try another device index or a
different USB port. If a model is missing, re-run `sh setup-pi.sh` or put the
two `.task` files in `models/`. To switch models during a session, stop the
camera, choose the other tracking input and restart it. `./launch.sh --models PATH`
accepts a different local model folder.

## References

- The [Electromaker tutorial](https://www.electromaker.io/project/view/kicker10bogdobotmagicianserver) informed the Pi USB setup, serial port selection and homing workflow.
- The [pydobot driver](https://github.com/luismesas/pydobot) and [Dobot Magician serial protocol](https://download.dobot.cc/product-manual/dobot-magician/pdf/en/Dobot-Communication-Protocol-V1.1.5.pdf) informed the standalone serial adapter.
- The [CircuitPath theme](https://github.com/jackallen28/BNTS_Circuit_Pathways/blob/BNTS_CircuitPath/ui/theme.css) informed the desktop styling.
- The [MediaPipe Python setup guide](https://developers.google.com/edge/mediapipe/solutions/setup_python), [Gesture Recognizer](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer) and [Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) cover the tracking models.
