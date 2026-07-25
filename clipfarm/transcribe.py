"""Local transcription with faster-whisper, plus audio loudness analysis."""

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import usage
from .config import ffmpeg_path


@dataclass
class Word:
    start: float
    end: float
    text: str


def transcribe(audio_path: Path, model_name: str, compute_type: str,
               cache_path: Path | None = None) -> list[Word]:
    """Transcribe with word timestamps. Caches to JSON so reruns are free."""
    if cache_path and cache_path.exists():
        data = json.loads(cache_path.read_text())
        return [Word(**w) for w in data]

    from faster_whisper import WhisperModel

    device, ct = "cpu", compute_type
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            device, ct = "cuda", "float16"
    except Exception:
        pass
    model = WhisperModel(model_name, device=device, compute_type=ct)
    segments, info = model.transcribe(
        str(audio_path), word_timestamps=True, vad_filter=True, language="en",
    )
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            words.append(Word(round(w.start, 2), round(w.end, 2), w.word.strip()))

    if cache_path:
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(w) for w in words]))
        tmp.replace(cache_path)  # atomic: parallel readers never see partials
    return words


def _groq_words(audio: Path, model: str, offset_s: float = 0.0,
                prompt: str = "") -> list[Word]:
    """One Groq transcription call -> Words shifted to absolute time.
    Retries through free-tier 429s."""
    import os
    import time

    import httpx

    for attempt in range(5):
        r = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            files={"file": (audio.name, audio.read_bytes())},
            data={"model": model, "response_format": "verbose_json",
                  "timestamp_granularities[]": "word", "language": "en",
                  **({"prompt": prompt[:220]} if prompt else {})},
            timeout=300,
        )
        if r.status_code == 429:
            wait = min(120, 20 * (attempt + 1))
            print(f"  groq rate limit, waiting {wait}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        payload = r.json()
        # Groq bills whisper per second of audio, not per token; verbose_json
        # already reports the duration it charged for.
        usage.record(model, audio_seconds=payload.get("duration") or 0.0)
        return [Word(round(w["start"] + offset_s, 2),
                     round(w["end"] + offset_s, 2), w["word"].strip())
                for w in (payload.get("words") or [])]
    raise RuntimeError("groq transcription rate-limited after 5 retries")


def transcribe_groq(audio_path: Path, cache_path: Path | None = None,
                    model: str = "whisper-large-v3-turbo",
                    chunk_minutes: int = 90) -> list[Word]:
    """Whole-VOD transcription via Groq (~200x realtime, no GPU anywhere).
    Long audio is re-encoded to small opus chunks (upload limit) with a 5s
    overlap; words landing in the overlap are taken from the later chunk."""
    import subprocess
    import tempfile

    if cache_path and cache_path.exists():
        data = json.loads(cache_path.read_text())
        return [Word(**w) for w in data]

    chunk_s = chunk_minutes * 60
    overlap = 5.0
    # probe duration
    p = subprocess.run(
        [ffmpeg_path(), "-i", str(audio_path), "-f", "null", "-t", "0.1", "-"],
        capture_output=True, text=True)
    import re as _re
    m = _re.search(r"Duration: (\d+):(\d+):(\d+\.?\d*)", p.stderr)
    dur = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
           + float(m.group(3))) if m else 0.0

    words: list[Word] = []
    t = 0.0
    with tempfile.TemporaryDirectory() as td:
        i = 0
        while t < max(dur, 0.1):
            chunk = Path(td) / f"chunk_{i:03d}.ogg"
            subprocess.run(
                [ffmpeg_path(), "-y", "-v", "error",
                 "-ss", str(max(0.0, t - (overlap if i else 0.0))),
                 "-t", str(chunk_s + overlap), "-i", str(audio_path),
                 "-vn", "-ac", "1", "-ar", "16000",
                 "-c:a", "libopus", "-b:a", "16k", str(chunk)],
                check=True, capture_output=True)
            off = max(0.0, t - (overlap if i else 0.0))
            got = _groq_words(chunk, model, offset_s=off)
            # overlap region belongs to this (later) chunk
            words = [w for w in words if w.start < t] + \
                    [w for w in got if w.start >= (t if i else 0.0)]
            print(f"  groq chunk {i + 1} "
                  f"({off / 60:.0f}-{min(dur, t + chunk_s) / 60:.0f}min): "
                  f"total {len(words)} words")
            t += chunk_s
            i += 1

    if cache_path:
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(w) for w in words]))
        tmp.replace(cache_path)
    return words


def transcribe_clips_groq(items: list[tuple[Path, float]],
                          model: str = "whisper-large-v3-turbo",
                          context: str = "",
                          max_workers: int = 3) -> list[list[Word]]:
    """Caption-grade transcription of clip segments via Groq — ~90s of audio
    costs ~$0.001 and returns in seconds.

    Each clip is independent. A small bounded pool overlaps local audio
    extraction with Groq uploads without creating an unbounded free-tier burst.
    Results retain input order.
    """
    from concurrent.futures import ThreadPoolExecutor
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)

        def one(index_item: tuple[int, tuple[Path, float]]) -> list[Word]:
            j, (media, offset_s) = index_item
            audio = temp / f"seg_{j:02d}.ogg"
            # a candidate whose audio can't be extracted (muted VOD section,
            # audio-less download) must drop out with empty words — it fails
            # arc verification downstream and the bench refills. One bad
            # candidate crashing the caption pass killed full 37-min jobs.
            ex = subprocess.run(
                [ffmpeg_path(), "-y", "-v", "error", "-i", str(media),
                 "-vn", "-ac", "1", "-ar", "16000",
                 "-c:a", "libopus", "-b:a", "16k", str(audio)],
                capture_output=True)
            if ex.returncode != 0 or not audio.exists() or not audio.stat().st_size:
                print(f"  ! segment {j + 1}: no usable audio "
                      f"({ex.stderr.decode()[-120:].strip() or 'empty output'})"
                      f" -> empty captions")
                return []
            # context prompt biases decoding — screamed/slurred lines
            # resolve to plausible words instead of gibberish
            return _groq_words(
                audio, model, offset_s=offset_s, prompt=context)

        workers = max(1, min(int(max_workers), len(items) or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(one, enumerate(items)))


def transcribe_clips(items: list[tuple[Path, float]], model_name: str,
                     compute_type: str) -> list[list[Word]]:
    """Accurate transcription of the chosen clip segments (burned captions
    only). items = [(media, absolute_start_s)]. A big model over ~90s of
    audio costs seconds — accuracy where it's actually visible."""
    from faster_whisper import WhisperModel

    device, ct = "cpu", compute_type
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            device, ct = "cuda", "float16"
    except Exception:
        pass
    model = WhisperModel(model_name, device=device, compute_type=ct)
    out: list[list[Word]] = []
    for media, offset_s in items:
        # same resilience rule as the groq path: a segment with undecodable
        # audio yields empty captions and drops out downstream, it never
        # kills the batch (av raises IndexError on audio-less files)
        try:
            segments, _ = model.transcribe(
                str(media), word_timestamps=True, vad_filter=True,
                language="en",
            )
            out.append([Word(round(w.start + offset_s, 2),
                             round(w.end + offset_s, 2), w.word.strip())
                        for seg in segments for w in (seg.words or [])])
        except Exception as e:
            print(f"  ! {Path(media).name}: transcription failed "
                  f"({type(e).__name__}: {str(e)[:80]}) -> empty captions")
            out.append([])
    return out


def loudness_profile(audio_path: Path, window_s: float = 1.0) -> np.ndarray:
    """Per-second RMS loudness (normalized 0..1). Index i = second i."""
    sr = 8000
    p = subprocess.run(
        [ffmpeg_path(), "-v", "error", "-i", str(audio_path),
         "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
        capture_output=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {p.stderr[-500:].decode()}")
    pcm = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    n = int(sr * window_s)
    usable = len(pcm) - (len(pcm) % n)
    if usable <= 0:
        return np.zeros(1)
    rms = np.sqrt((pcm[:usable].reshape(-1, n) ** 2).mean(axis=1))
    peak = rms.max() or 1.0
    return rms / peak


def energy_score(profile: np.ndarray, start: float, end: float) -> float:
    """Mean of top-25% loudness seconds inside [start, end] — spikes matter."""
    a, b = int(start), min(int(end) + 1, len(profile))
    if b <= a:
        return 0.0
    window = np.sort(profile[a:b])[::-1]
    top = window[: max(1, len(window) // 4)]
    return float(top.mean())
