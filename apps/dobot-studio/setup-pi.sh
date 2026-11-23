#!/bin/sh
# Install Python dependencies and the two MediaPipe models on Raspberry Pi OS.
set -eu
cd "$(dirname "$0")"

if [ "$(uname -m)" != aarch64 ] || [ "$(getconf LONG_BIT)" != 64 ]; then
    printf '%s\n' "Use 64-bit Raspberry Pi OS on the Pi 5." >&2
    exit 1
fi

if ! python3 -c 'import tkinter' 2>/dev/null; then
    printf '%s\n' "Install python3-tk and the other system packages listed in README.md." >&2
    exit 1
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
mkdir -p models

download_model() {
    if [ -s "models/$1" ]; then
        return
    fi
    temporary=$(mktemp "models/$1.XXXXXX")
    if ! curl --fail --location --retry 2 --output "$temporary" "$2"; then
        rm -f "$temporary"
        return 1
    fi
    mv "$temporary" "models/$1"
}

download_model gesture_recognizer.task \
    https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
download_model pose_landmarker_lite.task \
    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
printf '%s\n' "Setup complete. Run ./launch.sh on the Raspberry Pi desktop."
