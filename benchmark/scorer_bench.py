"""Scorer bench: same transcript chunks -> N models -> latency + picks,
then Claude (via local claude CLI, $0) blind-ranks pick quality.

Run:  python benchmark/scorer_bench.py path/to/transcript.json
Env:  GEMINI_API_KEY, GROQ_API_KEY
"""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clipfarm import detect  # noqa: E402
from clipfarm.transcribe import Word  # noqa: E402

CANDIDATES = [
    ("gpt-5-nano", "openai"),
    ("gpt-5-mini", "openai"),
    ("gemini-3.5-flash", "gemini"),
    ("gemini-3.1-flash-lite", "gemini"),
    ("qwen/qwen3.6-27b", "groq"),
    ("meta-llama/llama-4-scout-17b-16e-instruct", "groq"),
    ("llama-3.3-70b-versatile", "groq"),
]
BASE = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
    "openai": None,
}
KEY_ENV = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY",
           "openai": "OPENAI_API_KEY"}

# comedy-dense windows of the CaseOh test VOD (seconds)
WINDOWS = [(1900, 2400), (8600, 9100)]


def chunk_text(words, lo, hi):
    lines = detect._transcript_lines([w for w in words if lo <= w.start < hi])
    return "\n".join(f"[{int(t)}] {txt}" for t, txt in lines)


def run_model(model, provider, body):
    import os
    from openai import OpenAI
    kw = {"api_key": os.environ[KEY_ENV[provider]]}
    if BASE[provider]:
        kw["base_url"] = BASE[provider]
    client = OpenAI(**kw)
    t0 = time.time()
    data = detect._score_chunk_openai(
        client, model, body, detect.SYSTEM.format(streamer="caseoh_"))
    dt = time.time() - t0 - 7  # minus pacing sleep
    ms = [m for m in data.get("moments", []) if m.get("score", 0) >= 5]
    return dt, ms


def judge(results, body_by_window):
    """claude -p ranks anonymized candidates."""
    blob = ""
    for wi, body in enumerate(body_by_window):
        blob += f"\n=== TRANSCRIPT WINDOW {wi + 1} ===\n{body[:6000]}\n"
    for i, (model, _, picks_by_window) in enumerate(results):
        blob += f"\n=== CANDIDATE {chr(65 + i)} ===\n"
        for wi, picks in enumerate(picks_by_window):
            for m in picks[:4]:
                blob += (f"win{wi + 1} {m['start']}-{m['end']}s score{m['score']} "
                         f"| {m['title']} | hook: {m.get('hook', '')}\n")
    prompt = (
        "You judge clip-picking quality for gaming YouTube Shorts (streamer: CaseOh, "
        "loud comedy). Below: transcript windows, then candidates' picked moments with "
        "titles/hooks. Rank ALL candidates best->worst on: (1) picked genuinely funny "
        "peak moments with setup+punchline bounds, (2) title/hook quality for Shorts. "
        "Respond ONLY with JSON: {\"ranking\": [\"A\",...], \"notes\": {\"A\": \"one line\", ...}}"
        + blob)
    r = subprocess.run([str(Path.home() / ".npm-global/bin/claude"), "-p", prompt],
                       capture_output=True, text=True, timeout=600)
    return detect._extract_json(r.stdout)


def main(transcript_path):
    words = [Word(**w) for w in json.loads(Path(transcript_path).read_text())]
    bodies = [chunk_text(words, lo, hi) for lo, hi in WINDOWS]

    results = []
    for model, provider in CANDIDATES:
        lats, picks_all = [], []
        ok = True
        for body in bodies:
            try:
                dt, picks = run_model(model, provider, body)
                lats.append(dt)
                picks_all.append(picks)
            except Exception as e:
                print(f"{model}: FAILED ({str(e)[:80]})")
                ok = False
                break
        if ok:
            results.append((model, sum(lats) / len(lats), picks_all))
            print(f"{model}: {sum(lats)/len(lats):.1f}s avg, "
                  f"{sum(len(p) for p in picks_all)} picks")

    print("\n--- Claude judging (blind) ---")
    verdict = judge(results, bodies)
    label = {chr(65 + i): results[i][0] for i in range(len(results))}
    for rank, cand in enumerate(verdict["ranking"], 1):
        print(f"{rank}. {label.get(cand, cand)}  — {verdict['notes'].get(cand, '')}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else
         str(Path.home() / "clipfarm/work/2810132943/transcript.json"))
