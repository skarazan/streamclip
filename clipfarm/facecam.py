"""Locate the streamer's facecam box in a video segment via face detection."""

from pathlib import Path

import cv2
import numpy as np


def detect_facecam(video: Path, samples: int = 9) -> tuple[float, float, float, float] | None:
    """Return the facecam crop region as (x, y, w, h) fractions of the frame,
    or None if no stable face is found (e.g. cam hidden this scene)."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return None
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    W = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    H = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    boxes = []
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.15, minNeighbors=6,
            minSize=(int(H * 0.07), int(H * 0.07)))
        for (x, y, w, h) in faces:
            boxes.append((x, y, w, h))
    cap.release()

    if len(boxes) < 3:
        return None
    arr = np.array(boxes, dtype=float)
    cx = arr[:, 0] + arr[:, 2] / 2
    cy = arr[:, 1] + arr[:, 3] / 2
    mx, my = np.median(cx), np.median(cy)
    # keep detections near the median center — one stable cam, not game faces
    keep = arr[(np.abs(cx - mx) < W * 0.10) & (np.abs(cy - my) < H * 0.10)]
    if len(keep) < 3:
        return None
    x, y, w, h = np.median(keep, axis=0)

    # expand head box to a webcam-style crop (head + shoulders, some air above)
    cw = w * 2.7
    ch = h * 3.1
    cx0 = x + w / 2 - cw / 2
    cy0 = y - h * 0.9
    # clamp to frame
    cx0 = max(0.0, min(cx0, W - cw))
    cy0 = max(0.0, min(cy0, H - ch))
    cw = min(cw, W)
    ch = min(ch, H)
    return (cx0 / W, cy0 / H, cw / W, ch / H)
