"""Local camera capture and a fresh, single-slot recognition result."""
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic

HAND, POSE = "Hand gestures", "Body poses"
MODEL_FILES = {HAND: "gesture_recognizer.task", POSE: "pose_landmarker_lite.task"}
GESTURES = {"Thumb_Up": "A", "Victory": "B", "Closed_Fist": "Stop"}


@dataclass(frozen=True)
class Detection:
    command: str | None
    label: str
    tracked: bool
    timestamp: float


class GestureGate:
    def __init__(self):
        self.reset()

    def reset(self):
        self.candidate = None
        self.since = 0
        self.ready = False

    def observe(self, detection):
        if not detection.tracked:
            self.reset()
            return None
        action = detection.command
        if action == "Stop":
            self.reset()
            return "Stop"
        if action is None:
            self.reset()
            self.ready = True
            return None
        if not self.ready:
            return None
        if action != self.candidate:
            self.candidate = action
            self.since = detection.timestamp
        if detection.timestamp - self.since >= 0.35:
            self.ready = False
            return action
        return None


def classify_pose(landmarks):
    if not landmarks:
        return None, "No body in view", False
    points = landmarks[0]
    left_shoulder, right_shoulder, left_wrist, right_wrist = (points[i] for i in (11, 12, 15, 16))
    if any((point.visibility or 0) < 0.65 or (point.presence or 0) < 0.65
           for point in (left_shoulder, right_shoulder, left_wrist, right_wrist)):
        return None, "Show both wrists and shoulders", False
    left = left_shoulder.y - left_wrist.y
    right = right_shoulder.y - right_wrist.y
    if left >= 0.09 and right >= 0.09:
        return "Stop", "Both wrists raised", True
    if left >= 0.09 and right < 0.03:
        return "A", "Left wrist raised", True
    if right >= 0.09 and left < 0.03:
        return "B", "Right wrist raised", True
    if left < 0.03 and right < 0.03:
        return None, "Neutral pose", True
    return None, "Hold a clear pose", False


def classify_hand(result):
    if not result.hand_landmarks:
        return None, "No hand in view", False
    if not result.gestures or not result.gestures[0]:
        return None, "Hand detected", True
    category = result.gestures[0][0]
    if category.category_name in GESTURES:
        if category.score < 0.72:
            return None, "Hold a clear gesture", False
        return GESTURES[category.category_name], category.category_name.replace("_", " "), True
    return None, "Neutral hand", True


class Camera:
    def __init__(self, device, mode, models, report):
        self.device, self.mode, self.models, self.report = device, mode, Path(models), report
        self.stop = Event()
        self.lock = Lock()
        self.latest = None
        self.thread = Thread(target=self._run, daemon=True, name="camera")
        self.thread.start()

    def read(self):
        with self.lock:
            return self.latest

    def close(self):
        self.stop.set()

    def _run(self):
        capture = None
        try:
            model = self.models / MODEL_FILES[self.mode]
            if not model.is_file():
                raise RuntimeError(f"Model missing: {model.name}. See the setup guide.")
            import cv2
            import mediapipe as mp
            from PIL import Image

            task = mp.tasks.vision
            options = dict(base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
                           running_mode=task.RunningMode.VIDEO)
            if self.mode == HAND:
                detector = task.GestureRecognizer.create_from_options(task.GestureRecognizerOptions(**options))
            else:
                detector = task.PoseLandmarker.create_from_options(task.PoseLandmarkerOptions(**options))
            with detector:
                if self.stop.is_set():
                    return
                device = int(self.device) if self.device.isdecimal() else self.device
                capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
                if not capture.isOpened():
                    raise RuntimeError(f"Cannot open camera {self.device}. Check the USB connection and device.")
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                last_ms = -1
                while not self.stop.is_set():
                    ok, bgr = capture.read()
                    captured_at = monotonic()
                    if not ok:
                        raise RuntimeError("Camera stopped returning frames.")
                    height, width = bgr.shape[:2]
                    if width > 640:
                        bgr = cv2.resize(bgr, (640, max(1, round(height * 640 / width))))
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    last_ms = max(last_ms + 1, int(captured_at * 1000))
                    if self.mode == HAND:
                        result = detector.recognize_for_video(image, last_ms)
                        cmd, label, tracked = classify_hand(result)
                        landmarks = result.hand_landmarks[0] if result.hand_landmarks else []
                        indexes = range(len(landmarks))
                    else:
                        result = detector.detect_for_video(image, last_ms)
                        cmd, label, tracked = classify_pose(result.pose_landmarks)
                        landmarks = result.pose_landmarks[0] if result.pose_landmarks else []
                        indexes = (11, 12, 13, 14, 15, 16) if landmarks else ()
                    height, width = rgb.shape[:2]
                    for index in indexes:
                        point = landmarks[index]
                        cx, cy = round(point.x * width), round(point.y * height)
                        cv2.circle(rgb, (cx, cy), 5, (25, 193, 202), -1)
                        cv2.circle(rgb, (cx, cy), 5, (255, 255, 255), 1)
                    preview = Image.fromarray(rgb).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    with self.lock:
                        self.latest = Detection(cmd, label, tracked, captured_at), preview
        except Exception as error:
            if not self.stop.is_set():
                self.report(str(error))
        finally:
            if capture is not None:
                capture.release()
