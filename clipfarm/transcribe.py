"""Local transcription with faster-whisper, plus audio loudness analysis."""

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

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

    model = WhisperModel(model_name, device="cpu", compute_type=compute_type)
    segments, info = model.transcribe(
        str(audio_path), word_timestamps=True, vad_filter=True, language="en",
    )
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            words.append(Word(round(w.start, 2), round(w.end, 2), w.word.strip()))

    if cache_path:
        cache_path.write_text(json.dumps([asdict(w) for w in words]))
    return words


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
