"""Pick the funniest moments: Claude scores the transcript, loudness breaks ties."""

import json
from dataclasses import dataclass, field

import numpy as np

from .transcribe import Word, energy_score

MOMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "moments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "score": {"type": "integer"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["start", "end", "score", "title", "hook", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["moments"],
    "additionalProperties": False,
}

SYSTEM = """You find viral YouTube Shorts moments in Twitch stream transcripts.
The streamer is {streamer}: a gaming streamer. Viewers clip: big comedic
reactions, rage moments, absurd one-liners, chat interactions, screaming fits,
unexpected jokes, self-roasts, game fails with big verbal reactions.

You get transcript lines as `[seconds] text`. Return the strongest candidate
moments. Rules:
- score 1-10: 10 = guaranteed viral, 5 = decent, skip anything under 5
- start/end in seconds; capture the setup AND the reaction/punchline, nothing more
- moments must be 12-28 seconds long. Aim for 15-20 — short clips retain best.
  Cut every second of dead air; start as late as possible, end right after the
  punchline lands
- title: a clickable YouTube Shorts title, punchy, no clickbait lies, max 90 chars
- hook: a short on-screen overlay line (3-8 words, sentence case) that teases the
  moment without spoiling the punchline, e.g. "Can you guess why he is *mad*?" or
  "Still not *finished*...". Wrap exactly ONE emotional keyword in *asterisks* —
  it gets rendered in color.
- reason: one short sentence why it works
Return at most 8 moments per transcript chunk. Quality over quantity."""


@dataclass
class Moment:
    start: float
    end: float
    score: float
    title: str
    hook: str = ""
    reason: str = ""
    energy: float = 0.0
    combined: float = field(default=0.0)


def _transcript_lines(words: list[Word]) -> list[tuple[float, str]]:
    """Group words into ~8s lines: (start_time, text)."""
    lines, cur, cur_start = [], [], None
    for w in words:
        if cur_start is None:
            cur_start = w.start
        cur.append(w.text)
        if w.end - cur_start >= 8.0:
            lines.append((cur_start, " ".join(cur)))
            cur, cur_start = [], None
    if cur:
        lines.append((cur_start, " ".join(cur)))
    return lines


def _is_openai(model: str) -> bool:
    return model.startswith(("gpt-", "o1", "o3", "o4"))


def _claude_cli() -> str | None:
    import shutil
    from pathlib import Path
    found = shutil.which("claude")
    if found:
        return found
    for p in (Path.home() / ".npm-global/bin/claude",
              Path.home() / ".local/bin/claude"):
        if p.exists():
            return str(p)
    return None


def llm_available(model: str, base_url: str | None = None,
                  api_key_env: str | None = None) -> bool:
    import os
    if model == "claude-code":
        return _claude_cli() is not None
    if base_url:
        return bool(os.environ.get(api_key_env or "OPENAI_API_KEY"))
    if _is_openai(model):
        return bool(os.environ.get("OPENAI_API_KEY"))
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    # `ant auth login` profile on disk also works with the zero-arg client
    from pathlib import Path
    cfg_dir = Path.home() / ".config" / "anthropic" / "credentials"
    return cfg_dir.exists() and any(cfg_dir.glob("*.json"))


def _score_chunk_claude(client, model: str, body: str, system: str = None) -> dict:
    import anthropic
    kwargs = {}
    if not model.startswith("claude-haiku"):
        # adaptive thinking is supported on Opus 4.6+/Sonnet 4.6+, not Haiku 4.5
        kwargs["thinking"] = {"type": "adaptive"}
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=8000,
            system=system or SYSTEM,
            output_config={"format": {"type": "json_schema",
                                      "schema": MOMENT_SCHEMA}},
            messages=[{"role": "user", "content": body}],
            **kwargs,
        )
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"API error {e.status_code}") from e
    if resp.stop_reason == "refusal":
        return {"moments": []}
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text)


def _extract_json(text: str) -> dict:
    """Parse the first complete JSON object in possibly-chatty output."""
    a = text.find("{")
    if a == -1:
        raise json.JSONDecodeError("no JSON object found", text, 0)
    obj, _ = json.JSONDecoder().raw_decode(text[a:])
    return obj


def _score_chunk_claude_code(client, model: str, body: str, system: str = None) -> dict:
    """Score via the Claude Code CLI — runs on the user's Claude subscription,
    no API key needed."""
    import subprocess
    prompt = (
        (system or SYSTEM)
        + "\n\nRespond with ONLY a JSON object, no prose, matching exactly: "
        + json.dumps(MOMENT_SCHEMA)
        + "\n\nTranscript:\n" + body
    )
    r = subprocess.run(
        [_claude_cli() or "claude", "-p", prompt],
        capture_output=True, text=True, timeout=600,
    )
    if "Not logged in" in r.stdout:
        raise RuntimeError(
            "claude CLI not logged in — run `claude` in a terminal, type /login, "
            "choose your Claude subscription account")
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {r.stderr[-500:]}")
    return _extract_json(r.stdout)


def _score_chunk_openai(client, model: str, body: str, system: str = None) -> dict:
    """OpenAI-compatible endpoint (OpenAI, Groq, Gemini, OpenRouter, ...).
    Tries strict JSON schema first; many free endpoints don't support it,
    so falls back to prompt-enforced JSON."""
    import time as _time
    _time.sleep(7)  # pace for free-tier RPM limits instead of burst+429
    messages = [{"role": "system", "content": system or SYSTEM},
                {"role": "user", "content": body}]

    def _create(**kw):
        # free tiers rate-limit hard; back off and retry
        for attempt in range(5):
            try:
                return client.chat.completions.create(**kw)
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    _time.sleep(30 * (attempt + 1))
                    continue
                raise
        raise RuntimeError("rate-limited after 5 retries")

    try:
        kw = {}
        if "gemini-2.5" in model or "gemini-3" in model:
            kw["reasoning_effort"] = "none"
        resp = _create(
            model=model,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": {
                "name": "moments", "schema": MOMENT_SCHEMA, "strict": True}},
            **kw,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        pass  # endpoint likely doesn't support json_schema — degrade gracefully
    messages[1]["content"] = (
        body + "\n\nRespond with ONLY a JSON object, no prose, matching exactly: "
        + json.dumps(MOMENT_SCHEMA))
    try:
        resp = _create(model=model, messages=messages,
                       response_format={"type": "json_object"})
    except Exception:
        resp = _create(model=model, messages=messages)
    return _extract_json(resp.choices[0].message.content)


def score_with_llm(words: list[Word], model: str, chunk_minutes: int,
                   log=print, base_url: str | None = None,
                   api_key_env: str | None = None,
                   streamer: str = "the streamer") -> list[Moment]:
    if model == "claude-code":
        client = None
        score_chunk = _score_chunk_claude_code
    elif base_url:
        # any OpenAI-compatible endpoint: Groq, Gemini, OpenRouter free tiers...
        import os
        from openai import OpenAI
        client = OpenAI(base_url=base_url,
                        api_key=os.environ[api_key_env or "OPENAI_API_KEY"])
        score_chunk = _score_chunk_openai
    elif _is_openai(model):
        from openai import OpenAI
        client = OpenAI()
        score_chunk = _score_chunk_openai
    else:
        import anthropic
        client = anthropic.Anthropic()
        score_chunk = _score_chunk_claude

    lines = _transcript_lines(words)
    chunk_s = chunk_minutes * 60

    # split lines into time chunks
    chunks: list[list[tuple[float, str]]] = []
    cur, cur_t0 = [], 0.0
    for t, text in lines:
        if t - cur_t0 >= chunk_s and cur:
            chunks.append(cur)
            cur, cur_t0 = [], t
        cur.append((t, text))
    if cur:
        chunks.append(cur)

    moments: list[Moment] = []
    for i, chunk in enumerate(chunks, 1):
        log(f"  LLM scoring chunk {i}/{len(chunks)} "
            f"({chunk[0][0]/60:.0f}-{chunk[-1][0]/60:.0f} min)...")
        body = "\n".join(f"[{int(t)}] {text}" for t, text in chunk)
        try:
            data = score_chunk(client, model, body,
                               SYSTEM.format(streamer=streamer))
        except Exception as e:
            log(f"  ! chunk {i} failed ({type(e).__name__}: {e}), skipping")
            continue
        for m in data.get("moments", []):
            if m["score"] >= 5 and m["end"] > m["start"]:
                moments.append(Moment(
                    start=float(m["start"]), end=float(m["end"]),
                    score=float(m["score"]), title=m["title"],
                    hook=m.get("hook", ""), reason=m.get("reason", ""),
                ))
    return moments


def moments_from_energy(profile: np.ndarray, clip_len: float = 45.0,
                        top_n: int = 12) -> list[Moment]:
    """Fallback when no API key: pick loudest windows."""
    if len(profile) < clip_len:
        return [Moment(0, float(len(profile)), 5, "Stream highlight")]
    step = int(clip_len // 2)
    scored = []
    for start in range(0, len(profile) - int(clip_len), step):
        scored.append((energy_score(profile, start, start + clip_len), start))
    scored.sort(reverse=True)
    return [
        Moment(float(s), float(s + clip_len), 5.0, "Stream highlight",
               hook="It gets *crazy*...")
        for _, s in scored[:top_n]
    ]


def select_clips(moments: list[Moment], profile: np.ndarray, count: int,
                 min_len: float, max_len: float) -> list[Moment]:
    """Rank by LLM score + loudness, enforce length bounds and no overlap."""
    for m in moments:
        # clamp length
        if m.end - m.start > max_len:
            m.end = m.start + max_len
        if m.end - m.start < min_len:
            pad = (min_len - (m.end - m.start)) / 2
            m.start = max(0.0, m.start - pad)
            m.end = m.start + min_len
        m.energy = energy_score(profile, m.start, m.end)
        m.combined = m.score + 2.0 * m.energy  # loudness worth up to +2

    picked: list[Moment] = []
    for m in sorted(moments, key=lambda x: x.combined, reverse=True):
        if any(not (m.end <= p.start or m.start >= p.end) for p in picked):
            continue
        picked.append(m)
        if len(picked) == count:
            break
    return sorted(picked, key=lambda m: m.start)
