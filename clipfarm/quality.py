"""Deterministic quality gates for selected and rendered Shorts.

LLMs may propose a moment and edit plan, but they do not get to certify their
own work.  This module localizes trigger/button evidence in timestamped words,
checks chronology and payoff placement, verifies metadata claims, and inspects
the final media artifact.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .transcribe import Word


_TOKEN = re.compile(r"[a-z0-9]+")
_SCREAM_WORD = re.compile(
    r"^(?:a+h+|a+r+g+h+|o+h+|w+a+h+|e+e+k+|y+e+s+|n+o+|w+h+a+t+)$",
    re.I,
)
_DASHBOARD_TERMS = (
    "stream manager", "creator dashboard", "copyright claims",
    "monetization", "channel analytics", "revenue", "stream summary",
)

_DURATION_BUDGETS = {
    "stinger": (7.0, 12.0, 18.0),
    "soundbite": (8.0, 15.0, 22.0),
    "banter_roast": (10.0, 20.0, 28.0),
    "coincidence_verbal": (10.0, 20.0, 28.0),
    "physical_fail": (8.0, 16.0, 24.0),
    "rage_arc": (14.0, 25.0, 34.0),
    "bit_commitment": (14.0, 26.0, 36.0),
    "wholesome": (12.0, 24.0, 34.0),
}


def duration_budget(archetype: str) -> tuple[float, float, float]:
    """Return (minimum, target, hard maximum) seconds for an arc type."""
    return _DURATION_BUDGETS.get(
        (archetype or "other").lower(), (10.0, 22.0, 32.0))


def retained_duration_reason(
        intervals: list[tuple[float, float]],
        maximum: float = 45.0) -> str | None:
    """Reject only an overlong final edit, never its raw source span."""
    retained = sum(max(0.0, end - start) for start, end in intervals)
    if retained > maximum + 1e-6:
        return (
            f"retained story is {retained:.1f}s, above the "
            f"{maximum:.0f}s final duration limit"
        )
    return None


def low_substance_reason(decision: str, button_kind: str,
                         archetype: str) -> str | None:
    """Block loud-but-thin bench filler from satisfying an output quota."""
    del decision  # model approval cannot override structural thinness
    if (button_kind or "").lower() == "scream" and (
            "trivial" in (archetype or "").lower()):
        return "trivial-trigger scream is not a story"
    return None


def contextual_preroll(trigger_quote: str, trigger_role: str,
                       reason: str = "") -> float:
    """Context runway without blindly adding six quiet seconds."""
    quote = (trigger_quote or "").lower()
    rationale = (reason or "").lower()
    # The intent line itself explains the next action.
    if needs_visual_bridge(trigger_quote):
        return 1.0
    # A callout/outcome usually refers to the meaningful action immediately
    # before it (e.g. the cheer that chat is criticizing).
    if any(k in quote + " " + rationale for k in (
            "called out", "witnessed", "cheer", "what just happened")):
        return 6.0
    if (trigger_role or "").lower() in {"game", "npc", "video"}:
        return 2.5
    return 1.25


def needs_visual_bridge(trigger_quote: str, trigger_role: str = "",
                        button_kind: str = "") -> bool:
    """Whether active silence carries the causal action or visual payoff."""
    quote = (trigger_quote or "").lower()
    explicit_intent = any(k in quote for k in (
        "gotta ", "going to ", "let me ", "i'll ", "i will ",
        "we need ", "save him", "save her", "try to "))
    visual_payoff = (
        (trigger_role or "").lower() in {"game", "npc", "video"}
        and (button_kind or "").lower() in {"scream", "visual", "game_sound"}
    )
    return explicit_intent or visual_payoff


@dataclass(frozen=True)
class ActivityGap:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def longest_speech_gap(words: list[Word], start: float,
                       end: float) -> ActivityGap:
    """Longest interval without timestamped speech inside a proposed cut."""
    return max(speech_gaps(words, start, end),
               key=lambda g: g.duration,
               default=ActivityGap(start, start))


def speech_gaps(words: list[Word], start: float,
                end: float) -> list[ActivityGap]:
    """All speech-free intervals in chronological order."""
    ws = sorted(
        (w for w in words if w.end >= start and w.start <= end),
        key=lambda w: w.start)
    cursor = start
    gaps = []
    for word in ws:
        if word.start > cursor:
            gaps.append(ActivityGap(cursor, min(word.start, end)))
        cursor = max(cursor, min(word.end, end))
    if cursor < end:
        gaps.append(ActivityGap(cursor, end))
    return gaps


@dataclass(frozen=True)
class MotionResult:
    mean: float
    static_fraction: float


def visual_motion(video: Path, start: float, end: float,
                  sample_fps: float = 2.0) -> MotionResult:
    """Cheap visual activity measurement for a speech-free interval."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    if not cap.isOpened() or end - start < .5:
        cap.release()
        return MotionResult(0.0, 1.0)
    step = max(1, int(round(fps / sample_fps)))
    a, b = max(0, int(start * fps)), max(0, int(end * fps))
    values, previous = [], None
    for pos in range(a, b + 1, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                          (160, 90))
        if previous is not None:
            values.append(
                float(np.mean(cv2.absdiff(gray, previous))) / 255.0)
        previous = gray
    cap.release()
    if not values:
        return MotionResult(0.0, 1.0)
    values_a = np.asarray(values)
    return MotionResult(
        float(values_a.mean()), float(np.mean(values_a < .012)))


def inactive_gap_reason(gap_s: float, motion: MotionResult) -> str | None:
    """Reject long dead zones, while retaining silent but active gameplay."""
    if gap_s >= 8.0 and (
            motion.mean < .018 or motion.static_fraction >= .60):
        return (f"{gap_s:.1f}s speech-free low-motion gap "
                f"(motion {motion.mean:.3f})")
    return None


def should_cut_idle_gap(gap_s: float, motion: MotionResult,
                        preserve_active: bool = True) -> bool:
    """Cut silence unless active visuals are causally required."""
    if gap_s < 3.0:
        return False
    if not preserve_active:
        return True
    return motion.mean < .018 or motion.static_fraction >= .60


def remove_idle_gaps(start: float, end: float,
                     gaps: list[ActivityGap],
                     edge_pad: float = .35) -> list[tuple[float, float]]:
    """Subtract idle gap interiors while leaving breathing room at speech."""
    removals = []
    for gap in gaps:
        a, b = gap.start + edge_pad, gap.end - edge_pad
        if b - a >= 1.0:
            removals.append((a, b))
    if not removals:
        return [(start, end)]
    keep, cursor = [], start
    for a, b in sorted(removals):
        a, b = max(a, start), min(b, end)
        if a > cursor:
            keep.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < end:
        keep.append((cursor, end))
    return [(a, b) for a, b in keep if b - a >= .4]


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def is_scream_quote(text: str) -> bool:
    toks = _tokenize(text)
    if not toks:
        return False
    return all(_SCREAM_WORD.match(t) or len(set(t)) <= 3 for t in toks)


def _lcs_len(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    row = [0] * (len(b) + 1)
    for x in a:
        prev = 0
        for j, y in enumerate(b, 1):
            old = row[j]
            row[j] = prev + 1 if x == y else max(row[j], row[j - 1])
            prev = old
    return row[-1]


def _token_score(quote: list[str], candidate: list[str]) -> float:
    if not quote or not candidate:
        return 0.0
    q, c = Counter(quote), Counter(candidate)
    overlap = sum((q & c).values())
    precision = overlap / len(candidate)
    recall = overlap / len(quote)
    f1 = 2 * precision * recall / (precision + recall + 1e-9)
    ordered = _lcs_len(quote, candidate) / len(quote)
    return 0.7 * f1 + 0.3 * ordered


@dataclass(frozen=True)
class QuoteMatch:
    start: float
    end: float
    score: float
    text: str


def locate_quote(quote: str, words: list[Word],
                 threshold: float = 0.45,
                 limit: int = 8) -> list[QuoteMatch]:
    """Locate a noisy transcript quote with ordered token-window matching."""
    qt = _tokenize(quote)
    if not qt or not words:
        return []
    wt = [_tokenize(w.text) for w in words]
    flat = [(tok, i) for i, toks in enumerate(wt) for tok in toks]
    if not flat:
        return []
    qn = len(qt)
    raw: list[QuoteMatch] = []
    for width in range(max(1, qn - 2), qn + 5):
        for i in range(0, len(flat) - width + 1):
            chunk = flat[i:i + width]
            toks = [x[0] for x in chunk]
            score = _token_score(qt, toks)
            if score < threshold:
                continue
            a, b = chunk[0][1], chunk[-1][1]
            raw.append(QuoteMatch(words[a].start, words[b].end, score,
                                  " ".join(w.text for w in words[a:b + 1])))
    # Suppress duplicate windows around the same delivery.
    out: list[QuoteMatch] = []
    for match in sorted(raw, key=lambda m: (-m.score, m.end - m.start)):
        if all(abs(match.start - kept.start) > 1.0 for kept in out):
            out.append(match)
            if len(out) >= limit:
                break
    return sorted(out, key=lambda m: m.start)


def _profile_peak(profile: np.ndarray | None, start: float, end: float,
                  after: float) -> QuoteMatch | None:
    if profile is None or not len(profile):
        return None
    a = max(0, int(math.floor(max(start, after))))
    b = min(len(profile), int(math.ceil(end)) + 1)
    if b - a < 2:
        return None
    seg = np.asarray(profile[a:b], dtype=float)
    med = float(np.median(seg)) or 0.01
    i = int(np.argmax(seg))
    peak = float(seg[i])
    if peak < max(0.55, 2.0 * med):
        return None
    t = float(a + i)
    return QuoteMatch(t, min(end, t + 1.0), min(1.0, peak), "[acoustic spike]")


@dataclass
class ArcResult:
    passed: bool
    reason: str
    trigger: QuoteMatch | None = None
    button: QuoteMatch | None = None
    button_kind: str = "speech"
    tail_s: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def verify_arc(trigger_quote: str, button_quote: str, words: list[Word],
               start: float, end: float,
               button_kind: str = "speech",
               trigger_role: str = "unknown",
               button_role: str = "streamer",
               profile: np.ndarray | None = None,
               final: bool = False) -> ArcResult:
    """Verify a chronological trigger -> payoff arc.

    ``final=False`` is the permissive source-window gate. ``final=True`` is
    strict about payoff placement and tail length and is intended for the
    actual post-cut timeline.
    """
    if end <= start or not words:
        return ArcResult(False, "no timestamped speech")
    if button_role.lower() in {"game", "npc", "other", "video"}:
        return ArcResult(False, f"button belongs to {button_role}")

    trigger_matches = locate_quote(trigger_quote, words, threshold=0.38)
    if not trigger_matches:
        return ArcResult(False, "trigger quote not found")

    kind = (button_kind or "speech").lower()
    scream = kind == "scream" or is_scream_quote(button_quote)
    quoted_scream = is_scream_quote(button_quote)
    button_matches = locate_quote(button_quote, words, threshold=0.48)
    pairs: list[tuple[float, QuoteMatch, QuoteMatch]] = []
    for trigger in trigger_matches:
        candidates = button_matches
        if scream:
            if quoted_scream:
                peak = _profile_peak(profile, start, end, trigger.end)
                candidates = [peak] if peak else []
            else:
                # Editors quote the last intelligible line before a
                # nonverbal scream. Require BOTH that quote and a nearby
                # acoustic spike; otherwise a later game/UI sound can be
                # mistaken for the payoff while the quoted button is absent.
                corroborated = []
                for speech in button_matches:
                    peak = _profile_peak(
                        profile, max(start, speech.start - 1.0),
                        min(end, speech.end + 3.0),
                        max(trigger.end, speech.start - 1.0))
                    if peak:
                        corroborated.append(QuoteMatch(
                            speech.start, max(speech.end, peak.end),
                            min(speech.score, peak.score),
                            f"{speech.text} [acoustic spike]"))
                # Old cached VODs may predate loudness_raw.npy. The spoken
                # button can still prove chronology; only scream intensity is
                # unverified in that fallback.
                candidates = corroborated if profile is not None else button_matches
        for button in candidates:
            if button is None or button.start < trigger.start + 0.15:
                continue
            arc_len = button.end - trigger.start
            if arc_len < 1.0 or arc_len > 65.0:
                continue
            compact = min(0.25, arc_len / 260.0)
            score = trigger.score + button.score - compact
            pairs.append((score, trigger, button))
    if not pairs:
        return ArcResult(False, "no ordered trigger-to-button pair",
                         button_kind="scream" if scream else kind)

    _, trigger, button = max(
        pairs, key=lambda p: (p[0], -(p[2].end - p[1].start)))
    verified_kind = (
        "scream" if scream and profile is not None
        else "speech" if scream
        else kind
    )
    tail = max(0.0, end - button.end)
    duration = end - start
    button_pos = (button.end - start) / max(duration, 0.1)
    if final:
        min_button_pos = .35 if verified_kind == "scream" else .62
        tail_limit = 8.0 if verified_kind == "scream" else 1.25
        if button_pos < min_button_pos:
            return ArcResult(False, "button lands too early in final cut",
                             trigger, button, verified_kind, tail)
        if tail > tail_limit:
            return ArcResult(False, f"{tail:.1f}s remains after button",
                             trigger, button, verified_kind, tail)
    if trigger_role.lower() in {"unknown", ""} and trigger.start > start + .7 * duration:
        return ArcResult(False, "trigger appears too late",
                         trigger, button, "scream" if scream else kind, tail)
    return ArcResult(True, "ordered arc verified", trigger, button,
                     verified_kind, tail)


def closing_beat_end(words: list[Word], button_end: float, clip_end: float,
                     max_follow: float = 8.0,
                     max_gap: float = 2.0) -> float:
    """Keep a nearby spoken tag after a scream instead of ending on the yell."""
    end = button_end
    limit = min(clip_end, button_end + max_follow)
    for word in sorted(words, key=lambda w: w.start):
        if word.start < button_end:
            continue
        if word.start > limit or word.start - end > max_gap:
            break
        end = max(end, word.end)
    return end


def remap_profile(profile: np.ndarray | None,
                  intervals: list[tuple[float, float]]) -> np.ndarray | None:
    """Project a one-Hz VOD profile onto a jump-cut timeline."""
    if profile is None or not len(profile):
        return None
    pieces = []
    for start, end in intervals:
        a = max(0, int(math.floor(start)))
        b = min(len(profile), int(math.ceil(end)))
        if b > a:
            pieces.append(np.asarray(profile[a:b]))
    return np.concatenate(pieces) if pieces else np.array([], dtype=float)


def metadata_violations(title: str, hook: str, arc: ArcResult,
                        button_role: str = "streamer",
                        title_strategy: str = "curiosity") -> list[str]:
    """Reject unsupported high-stakes claims instead of shipping clickbait."""
    text = f"{title} {hook}".lower()
    problems = []
    if len(title.strip()) > 72:
        problems.append("title exceeds 72-character retention budget")
    if title_strategy == "curiosity" and re.search(r"\bthen\b", title.lower()):
        problems.append("curiosity title summarizes the sequence with 'then'")
    if arc.button and arc.button.text:
        button_tokens = {
            t for t in re.sub(r"[^a-z0-9 ]", " ", arc.button.text.lower()).split()
            if len(t) > 3
        }
        if button_tokens:
            hook_tokens = set(re.sub(
                r"[^a-z0-9 ]", " ", hook.lower()).split())
            leaked = len(button_tokens & hook_tokens) / len(button_tokens)
            if leaked >= .65:
                problems.append("on-screen hook reveals the verified payoff")
    if any(k in text for k in ("jumpscare", "jump scared", "scream", "screamed")):
        if arc.button_kind != "scream":
            problems.append("scream/jumpscare claim lacks acoustic button")
    if any(k in text for k in ("roasted", "insult")):
        if button_role.lower() in {"game", "npc", "other", "video"}:
            problems.append("roast payoff is not the streamer")
    if not arc.passed:
        problems.append("metadata describes an unverified arc")
    return problems


@dataclass
class MediaQA:
    passed: bool
    errors: list[str]
    warnings: list[str]
    duration: float = 0.0
    fps: float = 0.0
    dashboard_hits: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _ratio(value: str) -> float:
    try:
        a, b = value.split("/", 1)
        return float(a) / float(b)
    except Exception:
        return 0.0


def _dashboard_ocr(video: Path, samples: int = 8) -> tuple[int, list[str]]:
    """OCR a few gameplay-pane frames for persistent creator-dashboard UI."""
    import cv2

    if not shutil_which("tesseract"):
        return 0, ["tesseract unavailable; dashboard OCR skipped"]
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return 0, ["video could not be opened for OCR"]
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    hits = 0
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frames * (i + .5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        # The lower pane is gameplay in split mode; full-frame still benefits
        # from scanning its lower two thirds.
        crop = frame[int(frame.shape[0] * .40):]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=.65, fy=.65)
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            cv2.imwrite(tmp.name, gray)
            r = subprocess.run(
                ["tesseract", tmp.name, "stdout", "--psm", "11"],
                capture_output=True, text=True, timeout=15)
        text = r.stdout.lower()
        if any(term in text for term in _DASHBOARD_TERMS):
            hits += 1
    cap.release()
    return hits, []


def shutil_which(name: str) -> str | None:
    from shutil import which
    return which(name)


def inspect_media(video: Path, expected_duration: float | None = None,
                  run_ocr: bool = True,
                  max_duration: float = 45.0) -> MediaQA:
    """Hard delivery checks over the final MP4, plus conservative OCR QA."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height,avg_frame_rate,duration,"
        "sample_aspect_ratio,display_aspect_ratio",
        "-of", "json", str(video),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        return MediaQA(False, ["ffprobe failed"], [])
    data = json.loads(r.stdout)
    streams = data.get("streams") or []
    vs = next((s for s in streams if s.get("codec_type") == "video"), None)
    aus = next((s for s in streams if s.get("codec_type") == "audio"), None)
    errors, warnings = [], []
    duration = float((data.get("format") or {}).get("duration") or 0.0)
    fps = _ratio((vs or {}).get("avg_frame_rate") or "0/1")
    if not vs or (vs.get("width"), vs.get("height")) != (1080, 1920):
        errors.append("video is not 1080x1920")
    if vs and vs.get("sample_aspect_ratio") not in {"1:1", "1/1"}:
        errors.append(
            f"non-square pixels ({vs.get('sample_aspect_ratio') or 'unknown'})")
    if vs and vs.get("display_aspect_ratio") not in {"9:16", "9/16"}:
        errors.append(
            f"display aspect is not 9:16 "
            f"({vs.get('display_aspect_ratio') or 'unknown'})")
    if not aus:
        errors.append("audio stream missing")
    if abs(fps - 30.0) > 0.05:
        errors.append(f"output is not CFR 30fps ({fps:.2f})")
    vd = float((vs or {}).get("duration") or duration)
    ad = float((aus or {}).get("duration") or duration)
    if vd and ad and abs(vd - ad) > 0.10:
        errors.append(f"A/V duration mismatch {abs(vd-ad):.3f}s")
    if expected_duration is not None and abs(duration - expected_duration) > .35:
        errors.append("container duration differs from cut plan")
    if duration < 6 or duration > max_duration:
        errors.append(f"duration outside shipping bounds ({duration:.1f}s)")
    dashboard_hits = 0
    if run_ocr:
        dashboard_hits, ocr_warnings = _dashboard_ocr(video)
        warnings.extend(ocr_warnings)
        if dashboard_hits >= 2:
            errors.append(f"creator-dashboard UI found in {dashboard_hits} samples")
    return MediaQA(not errors, errors, warnings, duration, fps, dashboard_hits)
