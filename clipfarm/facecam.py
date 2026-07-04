"""Locate the streamer's facecam box in a video segment.

Uses YuNet (DNN face detector, few false positives) when the bundled model
is present, falling back to Haar cascades. A detection must be stable across
most sampled frames and must NOT sit dead-center (a centered face means IRL
full-frame content, where the no-split fallback is the right layout anyway).
"""

from pathlib import Path

import cv2
import numpy as np

_YUNET = Path(__file__).resolve().parent / "models" / "yunet.onnx"


def _detect_faces_yunet(det, frame) -> list[tuple[float, float, float, float]]:
    h, w = frame.shape[:2]
    det.setInputSize((w, h))
    _, faces = det.detect(frame)
    out = []
    for f in faces if faces is not None else []:
        if f[-1] >= 0.8:  # confidence
            out.append(tuple(f[:4]))
    return out


def _detect_faces_haar(cascade, frame) -> list[tuple[float, float, float, float]]:
    h = frame.shape[0]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.15, minNeighbors=8,
        minSize=(int(h * 0.07), int(h * 0.07)))
    return [tuple(map(float, f)) for f in faces]


def detect_facecam(video: Path, samples: int = 9) -> tuple[float, float, float, float] | None:
    """Return the facecam crop region as (x, y, w, h) fractions of the frame,
    or None if no stable off-center face is found."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return None
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    W = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    H = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

    if _YUNET.exists():
        det = cv2.FaceDetectorYN.create(str(_YUNET), "", (320, 320), 0.8)
        detect = lambda fr: _detect_faces_yunet(det, fr)  # noqa: E731
    else:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        detect = lambda fr: _detect_faces_haar(cascade, fr)  # noqa: E731

    boxes, frames_hit = [], 0
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        faces = detect(frame)
        if faces:
            frames_hit += 1
        boxes.extend(faces)
    cap.release()

    # must be present in most of the clip, not a flash of game imagery
    if frames_hit < max(5, samples // 2 + 1) or len(boxes) < 3:
        return None
    arr = np.array(boxes, dtype=float)
    cx = arr[:, 0] + arr[:, 2] / 2
    cy = arr[:, 1] + arr[:, 3] / 2
    mx, my = np.median(cx), np.median(cy)
    # one stable cam position, not faces wandering around a game scene
    keep = arr[(np.abs(cx - mx) < W * 0.08) & (np.abs(cy - my) < H * 0.08)]
    if len(keep) < max(4, samples // 2):
        return None
    # dead-center face = IRL/full-cam content -> full-frame layout serves it better
    if 0.33 * W < mx < 0.67 * W and 0.33 * H < my < 0.67 * H:
        return None

    x, y, w, h = np.median(keep, axis=0)
    # expand head box to a webcam-style crop (head + shoulders, some air above)
    cw = w * 2.7
    ch = h * 3.1
    cx0 = x + w / 2 - cw / 2
    cy0 = y - h * 0.9
    cx0 = max(0.0, min(cx0, W - cw))
    cy0 = max(0.0, min(cy0, H - ch))
    cw = min(cw, W)
    ch = min(ch, H)
    return (cx0 / W, cy0 / H, cw / W, ch / H)
