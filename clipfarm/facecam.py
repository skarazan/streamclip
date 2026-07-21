"""Locate the streamer's facecam in stream video.

Hard truth learned on reaction streamers: the screen is full of faces that
aren't the streamer (people in watched videos, photos, the streamer's own
stream preview), and OBS scene switches move the real cam around, so neither
"a stable face in this segment" nor "the same position all stream" is enough.

What actually survives every layout: the streamer's face is the SAME FACE all
stream. So: YuNet detects faces, SFace embeds them, probes spread across the
whole VOD vote on which identity is the streamer, and each clip segment is
searched for that identity.

Fallbacks, in order: identity match (yunet+sface) -> whole-VOD position
consensus (yunet only) -> full frame.
"""

from pathlib import Path

import cv2
import numpy as np

_MODELS = Path(__file__).resolve().parent / "models"
_YUNET = _MODELS / "yunet.onnx"
_SFACE = _MODELS / "sface.onnx"

MATCH_T = 0.363  # SFace cosine match threshold (opencv_zoo reference value)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _recognizer():
    if _SFACE.exists():
        return cv2.FaceRecognizerSF.create(str(_SFACE), "")
    return None


def _detect_faces_yunet(det, frame) -> list[np.ndarray]:
    """Full YuNet rows (box + landmarks), needed for SFace alignment."""
    h, w = frame.shape[:2]
    det.setInputSize((w, h))
    _, faces = det.detect(frame)
    return [f for f in (faces if faces is not None else []) if f[-1] >= 0.8]


def _detect_faces_haar(cascade, frame) -> list[np.ndarray]:
    h = frame.shape[0]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.15, minNeighbors=8,
        minSize=(int(h * 0.07), int(h * 0.07)))
    return [np.array(f, dtype=float) for f in faces]


def _expand_to_cam(x, y, w, h, W, H) -> tuple[float, float, float, float]:
    """Expand a head box to a webcam-style crop (head + shoulders, air above),
    returned as fractions of the frame."""
    cw = w * 2.7
    ch = h * 3.1
    cx0 = x + w / 2 - cw / 2
    cy0 = y - h * 0.9
    cx0 = max(0.0, min(cx0, W - cw))
    cy0 = max(0.0, min(cy0, H - ch))
    cw = min(cw, W)
    ch = min(ch, H)
    return (cx0 / W, cy0 / H, cw / W, ch / H)


def _motion(video: Path, box: tuple[float, float, float, float],
            samples: int = 4) -> float:
    """Mean frame-to-frame pixel change (0..1) inside the box. A live webcam
    moves; a photo shown on stream doesn't."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return 0.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    W = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    H = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    x, y = int(box[0] * W), int(box[1] * H)
    w, h = max(1, int(box[2] * W)), max(1, int(box[3] * H))
    crops = []
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / samples))
        ok, frame = cap.read()
        if ok:
            crops.append(cv2.cvtColor(frame[y:y + h, x:x + w],
                                      cv2.COLOR_BGR2GRAY).astype(np.float32))
    cap.release()
    if len(crops) < 2:
        return 0.0
    diffs = [np.abs(a - b).mean() / 255.0 for a, b in zip(crops, crops[1:])]
    return float(np.mean(diffs))


def detect_candidates(video: Path, samples: int = 9,
                      allow_center: bool = False,
                      min_frames: int | None = None,
                      conf: float = 0.8) -> list[dict]:
    """All stable face clusters in a segment, as candidate cam boxes:
    [{box, center, hits, motion, emb}]. emb is a mean SFace embedding, or
    None on the haar fallback path. `min_frames` overrides the stability
    filter (identity matching needs only a few matching frames — the face
    is confirmed by embedding, not by persistence); `conf` is the YuNet
    detection threshold (lower catches small/dark cam overlays)."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return []
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    W = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    H = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

    if _YUNET.exists():
        det = cv2.FaceDetectorYN.create(str(_YUNET), "", (320, 320), conf)
        detect = lambda fr: _detect_faces_yunet(det, fr)  # noqa: E731
    else:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        detect = lambda fr: _detect_faces_haar(cascade, fr)  # noqa: E731
    rec = _recognizer()

    clusters: list[dict] = []
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        for row in detect(frame):
            x, y, w, h = row[:4]
            emb = None
            if rec is not None and len(row) >= 15:
                try:
                    aligned = rec.alignCrop(frame, row)
                    emb = rec.feature(aligned).flatten()
                except cv2.error:
                    pass
            cx, cy = x + w / 2, y + h / 2
            for c in clusters:
                if abs(cx - c["cx"]) < W * 0.08 and abs(cy - c["cy"]) < H * 0.08:
                    c["boxes"].append((x, y, w, h))
                    c["frames"].add(i)
                    if emb is not None:
                        c["embs"].append(emb)
                    break
            else:
                clusters.append({"cx": cx, "cy": cy,
                                 "boxes": [(x, y, w, h)], "frames": {i},
                                 "embs": [emb] if emb is not None else []})
    cap.release()

    out = []
    floor = min_frames if min_frames is not None else max(4, samples // 2)
    for c in clusters:
        # stable through most of the clip, not a flash of game imagery
        if len(c["frames"]) < floor:
            continue
        x, y, w, h = np.median(np.array(c["boxes"], dtype=float), axis=0)
        mx, my = x + w / 2, y + h / 2
        # dead-center face usually = fullscreen cam / reaction main content,
        # where full-frame layout is right — unless the caller wants them
        # (identity probing does: fullscreen-cam scenes are the streamer)
        if not allow_center and (0.33 * W < mx < 0.67 * W
                                 and 0.33 * H < my < 0.67 * H):
            continue
        box = _expand_to_cam(x, y, w, h, W, H)
        motion = _motion(video, box)
        if motion < 0.008:  # static image of a face shown on stream
            continue
        emb = None
        if c["embs"]:
            emb = np.mean(np.array(c["embs"]), axis=0)
            emb /= np.linalg.norm(emb) + 1e-9
        out.append({"box": box, "center": (mx / W, my / H),
                    "hits": len(c["frames"]), "motion": motion, "emb": emb})
    return out


def pick_vod_box(cand_lists: list[list[dict]],
                 need: int | None = None) -> tuple | None:
    """Position-consensus fallback (no recognizer): the box that recurs at
    the same spot across time-separated samples."""
    n_segs = sum(1 for cl in cand_lists)
    if need is None:
        need = 2 if n_segs >= 2 else 1
    groups: list[dict] = []
    for si, cl in enumerate(cand_lists):
        for c in cl:
            for g in groups:
                if (abs(c["center"][0] - g["center"][0]) < 0.06
                        and abs(c["center"][1] - g["center"][1]) < 0.06):
                    g["segs"].add(si)
                    g["cands"].append(c)
                    break
            else:
                groups.append({"center": c["center"], "segs": {si},
                               "cands": [c]})
    groups = [g for g in groups if len(g["segs"]) >= need]
    if not groups:
        return None
    # most segments wins; corner-most breaks ties (cams live at edges,
    # reaction content lives near the middle)
    def edge_dist(g):
        cx, cy = g["center"]
        return max(abs(cx - 0.5), abs(cy - 0.5))
    best = max(groups, key=lambda g: (len(g["segs"]), edge_dist(g),
                                      sum(c["hits"] for c in g["cands"])))
    arr = np.array([c["box"] for c in best["cands"]], dtype=float)
    return tuple(float(v) for v in np.median(arr, axis=0))


def identity_from_probes(cand_lists: list[list[dict]],
                         log=print) -> np.ndarray | None:
    """The streamer = the face identity that shows up across the most
    time-separated probes. Content faces are diverse; theirs isn't."""
    ids: list[dict] = []
    probed = 0
    for si, cl in enumerate(cand_lists):
        if cl:
            probed += 1
        for c in cl:
            if c.get("emb") is None:
                continue
            for g in ids:
                if _cosine(c["emb"], g["emb"]) >= MATCH_T:
                    g["probes"].add(si)
                    g["members"].append(c)
                    m = np.mean([x["emb"] for x in g["members"]], axis=0)
                    g["emb"] = m / (np.linalg.norm(m) + 1e-9)
                    break
            else:
                ids.append({"emb": c["emb"], "probes": {si}, "members": [c]})
    if not ids:
        return None
    best = max(ids, key=lambda g: (len(g["probes"]),
                                   sum(m["hits"] for m in g["members"])))
    need = max(2, (probed + 1) // 3)
    if len(best["probes"]) < need:
        log(f"  no identity spans enough probes "
            f"(best {len(best['probes'])}/{probed}, need {need})")
        return None
    log(f"  streamer identity locked ({len(best['probes'])}/{probed} probes)")
    return best["emb"]


def probe_vod(vod_url: str, duration_s: float, work_dir: Path,
              quality: str, n_probes: int = 8,
              probe_len: float = 2.0, log=print):
    """Probe tiny slices across the WHOLE stream. Returns (identity_emb,
    position_box) — either may be None. Identity survives OBS scene switches;
    the position box is the no-recognizer fallback."""
    from concurrent.futures import ThreadPoolExecutor

    from . import fetch

    def _probe(i: int) -> list[dict]:
        t = duration_s * (i + 0.5) / n_probes
        probe = work_dir / f"cam_probe_{i:02d}.mp4"
        try:
            if not probe.exists():
                fetch.download_segment(vod_url, t, t + probe_len, probe, quality)
            # centered faces allowed here: fullscreen-cam scenes are prime
            # identity evidence even though they render full-frame
            return detect_candidates(probe, samples=5, allow_center=True)
        except Exception as e:
            log(f"  cam probe {i + 1}/{n_probes} failed: {str(e)[:80]}")
            return []
        finally:
            probe.unlink(missing_ok=True)

    with ThreadPoolExecutor(max_workers=4) as ex:
        cand_lists = list(ex.map(_probe, range(n_probes)))
    hits = sum(1 for cl in cand_lists if cl)
    log(f"  cam probes: faces in {hits}/{len(cand_lists)} slices")
    identity = identity_from_probes(cand_lists, log=log)
    pos_box = pick_vod_box(cand_lists, need=max(2, (hits + 1) // 2)) if hits else None
    return identity, pos_box


def match_segment(video: Path, identity: np.ndarray,
                  samples: int = 18) -> tuple | None:
    """This segment's cam box: the off-center face that IS the streamer.
    None when the streamer isn't visible off-center (fullscreen cam, no cam,
    cam hidden) — full frame is the right layout then."""
    # lenient: matching against a KNOWN identity is reliable from few frames,
    # so catch small/dark/intermittent cam overlays (horror games) that the
    # strict stability+confidence filter was dropping -> false "no cam"
    cands = detect_candidates(video, samples, min_frames=3, conf=0.6)
    matches = [c for c in cands
               if c["emb"] is not None and _cosine(c["emb"], identity) >= MATCH_T]
    if not matches:
        return None
    # corner-most first, smaller box on ties (a video of the streamer is
    # bigger and closer to center than their cam overlay)
    best = max(matches, key=lambda c: (max(abs(c["center"][0] - 0.5),
                                           abs(c["center"][1] - 0.5)),
                                       -c["box"][2]))
    return best["box"]


def detect_facecam(video: Path, samples: int = 9) -> tuple[float, float, float, float] | None:
    """Single-segment convenience wrapper: corner-most stable live face,
    or None. Identity-aware callers should use probe_vod + match_segment."""
    cands = detect_candidates(video, samples)
    if not cands:
        return None
    best = max(cands, key=lambda c: (max(abs(c["center"][0] - 0.5),
                                         abs(c["center"][1] - 0.5)), c["hits"]))
    return best["box"]
