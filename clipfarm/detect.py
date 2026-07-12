"""Pick the funniest moments: Claude scores the transcript, loudness breaks ties."""

import json
from dataclasses import dataclass, field

import numpy as np

from .transcribe import Word, energy_score

PACING = 7  # seconds between scoring calls; 0 for paid providers

# reason comes FIRST: the model writes its case before it commits to numbers
# (CoT-before-score — measurably less variance than score-then-justify)
MOMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "moments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "self_contained": {"type": "boolean"},
                    "has_button": {"type": "boolean"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "score": {"type": "integer"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                },
                "required": ["reason", "self_contained", "has_button",
                             "start", "end", "score", "title", "hook"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["moments"],
    "additionalProperties": False,
}

# per-streamer selection rubrics + few-shot anchors. Anchors are REAL results
# from this channel's analytics (research/analytics-intel.md) — they calibrate
# the score scale and the title formula. Refresh as new data lands.
PERSONAS = {
    "caseoh": """{streamer} is a loud, physically expressive comedic streamer.
His best clips: sudden register shifts (normal talk -> all-caps scream inside
1-2 sentences), self-interrupting broken speech ("WAIT— NO— NO NO—"), comedic
overreactions to small triggers. Strong clips have a three-beat shape:
something happens -> big reaction/scream -> a TAG JOKE riffing on it a few
seconds later. A scream with no tag is usually incomplete — extend a few
seconds to catch the button. A hard topic-switch right after the peak is a
clean out-point.
CHANNEL DATA: reaction-framed titles win ("panicked so hard he caused a
tornado" 3.1k views) over object-framing ("summons a tornado with his weight"
0.9k). Include CASEOH in titles.""",
    "jynxzi": """{streamer} is a high-energy competitive gaming streamer whose
best clips are rage or hype moments tied to gameplay OUTCOMES. Look for
profanity-density spikes, chained short exclamations ("LET'S GOOO", "NO WAY"),
and game-state callouts (clutch, ace, 1v4, goal, rank-up) near the energy
spike. Rage/hype arcs build over 30-90s — cut from the TOP of the escalation,
not just the loudest word. A teammate/chat reaction line after the peak
("bro...", "what") is the button — include it. Generic complaining with no
gameplay payoff reads unlikeable, never clip it.
CHANNEL DATA: stakes-in-title wins big — "JYNXZI AMAZING GOAL IN ROCKETLEAGUE"
21k views, "JYNXZI is 2 WINS AWAY from DIAMOND" 11.5k. Generic verb titles
flop — "JYNXZI scores a POWER SHOT" (same game!) got 26 views. ALWAYS name
JYNXZI + the stakes/outcome, with the peak moment word in CAPS.""",
    "generic": """{streamer} is a gaming streamer. Viewers clip: big comedic
reactions, rage moments, absurd one-liners, chat interactions, screaming fits,
unexpected jokes, self-roasts, game fails with big verbal reactions.""",
}

SYSTEM = """You are the lead editor of a Twitch highlights Shorts channel. You
find moments a professional clip editor would cut into a standalone 15-28s
YouTube Short. You are ruthless: most of any stream is NOT clip-worthy, and a
mediocre pick wastes an upload slot.

{persona}

You get transcript lines as `[seconds] text`. Delivery tags measured from the
actual audio: [SCREAM]/[loud] = volume, [rapid] = excited fast speech,
`[pause Ns]` between lines = N seconds of silence (a pause right after a peak
is a comedic beat and a clean out-point; long pauses are dead air the render
will jump-cut). `[chat exploding: N msgs/5s]` = the live Twitch chat spiked
at that moment — strong evidence the crowd saw something clip-worthy; look
for what triggered it just BEFORE the spike (chat lags the moment by a few
seconds). Untagged lines were spoken at normal volume. Rules:
- write `reason` FIRST for every moment (2-3 sentences: what happens, what the
  hook is, what the button/payoff is) — then set the fields to match it
- self_contained: true only if it lands with ZERO outside context. A moment
  needing anything from 10 minutes earlier fails, no matter how funny
- has_button: true if the clip ends on a payoff (tag joke, reveal, reaction
  line) rather than trailing off after the peak
- score 1-10, calibrated against the WHOLE multi-hour stream, not this chunk:
  10 = the best moment of the entire stream, 8-9 = elite (most chunks have
  NONE), 6-7 = solid, 5 = borderline. Skip anything under 5. Never inflate —
  a boring chunk should return zero or low-scored moments
- delivery is content: a "rage moment" or "screaming fit" claim REQUIRES
  [SCREAM]/[loud] tags at its peak. A quietly muttered line is not a meltdown,
  and disbelief repeated in a normal voice is not "losing it"
- CRITICAL: the transcript mixes the STREAMER's voice with in-game dialogue
  (NPCs, cutscenes, videos on screen). Only the streamer's own reactions count —
  loud, first-person, addressed to chat or the game. NEVER pick a moment whose
  highlight is a game character's line; game dialogue can only be setup for the
  streamer's reaction
- start/end in seconds; capture the setup AND the reaction/punchline, nothing more
- moments must be 12-28 seconds long. Aim for 15-20 — short clips retain best.
  Cut dead air BEFORE the moment; start as late as possible. But NEVER cut the
  ending short: the reaction must fully play out — screams, laughter, the
  follow-up line. End 2-3 seconds AFTER the reaction settles, not mid-reaction.
  If the moment involves a guess, answer, or reveal (word games, quizzes,
  "wait is it X?"), the clip MUST include the reveal and the reaction to it —
  never end during the guessing
- title formula (from this channel's real analytics): STREAMER NAME + the
  stakes/outcome + the peak moment word in CAPS. "JYNXZI AMAZING GOAL IN
  ROCKETLEAGUE" got 21,000 views; "JYNXZI scores a POWER SHOT" (same game, no
  stakes, generic verb) got 26. Max 90 chars, no clickbait lies
- hook: a short on-screen overlay line (3-8 words, sentence case) that teases the
  moment without spoiling the punchline, e.g. "Can you guess why he is *mad*?" or
  "Still not *finished*...". Wrap exactly ONE emotional keyword in *asterisks* —
  it gets rendered in color.
- reason: one short sentence why it works
Return at most 8 moments per transcript chunk. Quality over quantity."""


RERANK_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "post_score": {"type": "integer"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "post_score", "start", "end",
                             "title", "hook", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}

EDITOR = """You are the final-approval editor at a Twitch clips channel. A
scorer proposed candidate Shorts from {streamer}'s stream — but it graded each
10-minute window in isolation, on a curve. Your job is RELATIVE: judge the
candidates head-to-head against each other, and pick what actually gets
posted. Most candidates are NOT worth posting — the channel's reputation is
"3 post-ready bangers, not 100 maybes".

{persona}

For close calls, explicitly compare the two candidates in your reasoning —
which first-2-seconds is the stronger scroll-stopper, which has the cleaner
button — before scoring. A mid-tier moment with an exceptional hook beats a
richer moment that opens slow. Judge each candidate's post_score 1-10
(7 = the bar for posting):
- DISTRUST high loudness + thin reasoning: that pattern means the scorer keyed
  off volume, not payoff. Loud-but-boring is the #1 false positive
- MID-SAG check: a great open and a great peak with 10 flat seconds between
  them retains nobody. The energy must hold or build through the middle
- one clear peak beat that lands with ZERO stream context
- escalation: it builds to the peak; flat-voiced repetition is filler, not
  drama, no matter how strong the words are
- delivery: measured loudness is given per candidate (0..1). Genuine
  screaming/meltdown is >= 0.40; below that, rage/"loses it" claims are false
- the peak must sit in the FINAL third: everything after the punchline is
  retention poison. If the source rambles on after the peak, cut the end to
  2-3s after the peak lands
- trim slow setup: start as late as possible while the joke stays legible
- VARIETY: the kept set is posted together as one batch. When candidates are
  the same bit, topic, or moment type (three screams about the same match =
  one clip), keep only the strongest and score the rest below the bar
Also return tightened start/end as ABSOLUTE stream seconds — transcript lines
carry [seconds] markers; anchor your cuts to them, never to offsets within the
snippet. Stay within 10s of the suggestion, 12-28s long, peak in the final
third. Return a sharper title + hook when you can.
hook: 3-8 words, sentence case, exactly ONE emotional keyword wrapped in
*asterisks*, never spoils the punchline.
Be ruthless: returning ZERO keeps is a valid, respected answer."""


def speech_gated(profile: np.ndarray, words: list[Word],
                 slack_s: float = 3.0) -> np.ndarray:
    """Zero out loudness where nobody is talking. Intro music, soundboards and
    game audio measure loud but aren't the streamer; a real scream sits within
    a few seconds of transcribed speech."""
    gated = np.zeros_like(profile)
    n = len(profile)
    for w in words:
        a = max(0, int(w.start - slack_s))
        b = min(n, int(w.end + slack_s) + 1)
        gated[a:b] = profile[a:b]
    # the raw profile is normalized to the whole-VOD peak — often intro music.
    # renormalize to the speech peak so scream thresholds mean screams.
    peak = gated.max()
    return gated / peak if peak > 0 else gated


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
    edited: bool = False  # boundaries hand-tightened by the editor pass


def _transcript_lines(words: list[Word],
                      profile: np.ndarray | None = None) -> list[tuple[float, str]]:
    """Group words into ~8s lines: (start_time, text). With a loudness profile,
    lines are tagged [SCREAM]/[loud] so a text-only model can hear delivery —
    without this it can't tell a genuine meltdown from a muttered one-liner."""
    lines, cur, cur_start = [], [], None

    def _flush(start: float, end: float) -> None:
        text = " ".join(cur)
        dur = max(end - start, 0.5)
        if len(cur) / dur >= 4.2:  # excited fast talk — free excitement signal
            text = "[rapid] " + text
        if profile is not None and len(profile):
            peak = float(profile[int(start):int(end) + 1].max(initial=0.0))
            if peak >= 0.70:
                text = "[SCREAM] " + text
            elif peak >= 0.45:
                text = "[loud] " + text
        lines.append((start, text))

    prev_end = None
    for w in words:
        if cur_start is None:
            cur_start = w.start
            # surface silence between lines: comedic beats and dead air are
            # invisible in text otherwise, and both matter for cut points
            if prev_end is not None and w.start - prev_end >= 2.0:
                lines.append((prev_end, f"[pause {w.start - prev_end:.0f}s]"))
        cur.append(w.text)
        if w.end - cur_start >= 8.0:
            _flush(cur_start, w.end)
            cur, cur_start, prev_end = [], None, w.end
    if cur:
        _flush(cur_start, words[-1].end)
    return lines


def _chat_spike_lines(chat: list[tuple[float, float]] | None
                      ) -> list[tuple[float, str]]:
    """Chat-density spikes -> [chat exploding] pseudo-transcript lines. The
    crowd reacts to the same beats a viewer would (PogChampNet's recall
    signal); volume only — chat sentiment is sarcasm-poisoned. Input is
    (t, msgs_per_sec) samples from fetch.download_chat."""
    if not chat:
        return []
    rates = np.array([r for _, r in chat])
    thresh = max(rates.mean() + 2.0 * rates.std(), 1.5)
    lines, prev = [], -1e9
    for (t, r) in chat:
        if r >= thresh and t - prev >= 60:  # one line per burst
            lines.append((t, f"[chat exploding: {r:.0f} msgs/s]"))
            prev = t
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
                  api_key_env: str | None = None,
                  fallback_models: list[str] | None = None) -> bool:
    import os
    # chain-aware: any credential for any rung means scoring can proceed
    if fallback_models:
        for name in [model] + fallback_models:
            if name.startswith("gemini") and os.environ.get("GEMINI_API_KEY"):
                return True
            if _is_openai(name) and os.environ.get("OPENAI_API_KEY"):
                return True
            if not name.startswith(("gemini", "gpt-", "claude")) \
                    and os.environ.get("GROQ_API_KEY"):
                return True
    if model.startswith("claude-code"):
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


def _score_chunk_claude(client, model: str, body: str, system: str = None,
                        schema: dict = None) -> dict:
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
                                      "schema": schema or MOMENT_SCHEMA}},
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


def _score_chunk_claude_code(client, model: str, body: str, system: str = None,
                             schema: dict = None) -> dict:
    """Score via the Claude Code CLI — runs on the user's Claude subscription,
    no API key needed."""
    import subprocess
    prompt = (
        (system or SYSTEM)
        + "\n\nRespond with ONLY a JSON object, no prose, matching exactly: "
        + json.dumps(schema or MOMENT_SCHEMA)
        + "\n\nTranscript:\n" + body
    )
    # "claude-code" = CLI default model; "claude-code:opus" etc. pins one
    cmd = [_claude_cli() or "claude", "-p", prompt]
    if ":" in model:
        cmd += ["--model", model.split(":", 1)[1]]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if "Not logged in" in r.stdout:
        raise RuntimeError(
            "claude CLI not logged in — run `claude` in a terminal, type /login, "
            "choose your Claude subscription account")
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {r.stderr[-500:]}")
    return _extract_json(r.stdout)


def _score_chunk_openai(client, model: str, body: str, system: str = None,
                        schema: dict = None) -> dict:
    """OpenAI-compatible endpoint (OpenAI, Groq, Gemini, OpenRouter, ...).
    Tries strict JSON schema first; many free endpoints don't support it,
    so falls back to prompt-enforced JSON."""
    import time as _time
    schema = schema or MOMENT_SCHEMA
    if PACING:
        _time.sleep(PACING)  # free tiers only; paid providers run unpaced
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
                "name": "moments", "schema": schema, "strict": True}},
            **kw,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        pass  # endpoint likely doesn't support json_schema — degrade gracefully
    messages[1]["content"] = (
        body + "\n\nRespond with ONLY a JSON object, no prose, matching exactly: "
        + json.dumps(schema))
    try:
        resp = _create(model=model, messages=messages,
                       response_format={"type": "json_object"})
    except Exception:
        resp = _create(model=model, messages=messages)
    return _extract_json(resp.choices[0].message.content)


def _fn_for(name: str):
    if name.startswith("claude-code"):
        return _score_chunk_claude_code
    if name.startswith("claude"):
        return _score_chunk_claude
    return _score_chunk_openai


def _client_provider(primary: str, base_url: str | None,
                     api_key_env: str | None):
    """Lazy per-model client cache, shared by scoring and the editor pass."""
    _clients = {}

    def _client_for(name: str):
        if name in _clients:
            return _clients[name]
        import os
        from openai import OpenAI
        if name.startswith("claude-code"):
            c = None
        elif name.startswith("claude"):
            import anthropic
            c = anthropic.Anthropic()
        elif name == primary and base_url:
            c = OpenAI(base_url=base_url,
                       api_key=os.environ[api_key_env or "OPENAI_API_KEY"])
        elif name.startswith("gemini"):
            c = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                       api_key=os.environ["GEMINI_API_KEY"])
        elif _is_openai(name):
            c = OpenAI()
        else:  # llama/qwen/etc -> Groq
            c = OpenAI(base_url="https://api.groq.com/openai/v1",
                       api_key=os.environ["GROQ_API_KEY"])
        _clients[name] = c
        return c

    return _client_for


def score_with_llm(words: list[Word], model: str, chunk_minutes: int,
                   log=print, base_url: str | None = None,
                   api_key_env: str | None = None,
                   streamer: str = "the streamer",
                   fallback_models: list[str] | None = None,
                   profile: np.ndarray | None = None,
                   persona: str = "generic",
                   chat: list[tuple[float, str]] | None = None
                   ) -> list[Moment]:
    _models = [model] + [m for m in (fallback_models or []) if m != model]
    persona_txt = PERSONAS.get(persona, PERSONAS["generic"]).format(
        streamer=streamer)
    system = SYSTEM.format(persona=persona_txt)
    _client_for = _client_provider(model, base_url, api_key_env)

    lines = sorted(_transcript_lines(words, profile)
                   + _chat_spike_lines(chat), key=lambda x: x[0])
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

    global PACING
    paid = model.startswith(("gpt-", "o1", "o3", "o4")) and not base_url
    PACING = 0 if paid else 7
    workers = 6 if paid else 1

    import threading
    from concurrent.futures import ThreadPoolExecutor
    done_count = [0]
    lock = threading.Lock()

    def _score_one(args):
        i, chunk = args
        body = "\n".join(f"[{int(t)}] {text}" for t, text in chunk)
        data = None
        for m_i, m_name in enumerate(list(_models)):
            try:
                data = _fn_for(m_name)(_client_for(m_name), m_name, body,
                                       system)
                if m_i > 0:
                    with lock:
                        log(f"  (scored with fallback model {m_name})")
                        _models[:] = _models[m_i:]  # stay on the working model
                break
            except Exception as e:
                with lock:
                    log(f"  ! chunk {i} on {m_name} failed "
                        f"({type(e).__name__}: {str(e)[:80]})")
        with lock:
            done_count[0] += 1
            log(f"  LLM scoring chunk {done_count[0]}/{len(chunks)} scored")
        return data

    with ThreadPoolExecutor(max_workers=workers) as ex:
        chunk_results = list(ex.map(_score_one, enumerate(chunks, 1)))

    moments: list[Moment] = []
    for data in chunk_results:
        if data is None:
            continue
        for m in data.get("moments", []):
            # the model wrote the reason first, then committed to this; a
            # context-dependent moment is dead on arrival for a Short
            if not m.get("self_contained", True):
                continue
            if m["score"] >= 5 and m["end"] > m["start"]:
                moments.append(Moment(
                    start=float(m["start"]), end=float(m["end"]),
                    score=float(m["score"]), title=m["title"],
                    hook=m.get("hook", ""), reason=m.get("reason", ""),
                ))
    return moments


def rerank_moments(moments: list[Moment], words: list[Word],
                   profile: np.ndarray, model: str, log=print,
                   base_url: str | None = None,
                   api_key_env: str | None = None,
                   streamer: str = "the streamer",
                   fallback_models: list[str] | None = None,
                   shortlist: int = 15, post_bar: int = 7,
                   persona: str = "generic") -> list[Moment]:
    """Editor pass: chunk scoring grades on a curve (every chunk hands out
    10s), so the shortlist gets re-judged head-to-head in ONE call, with the
    measured loudness and full transcript context the chunk scorer never saw.
    Only candidates clearing the posting bar survive; boundaries/titles/hooks
    come back tightened."""
    if len(moments) <= 1:
        return moments
    # a clip window must contain actual speech — hallucinated timestamps and
    # music-only stretches have none, no matter how loud they measured
    starts = np.array([w.start for w in words])
    moments = [m for m in moments
               if np.searchsorted(starts, m.end) - np.searchsorted(starts, m.start) >= 8]
    if not moments:
        return []
    for m in moments:
        m.energy = energy_score(profile, m.start, m.end)
        m.combined = m.score + 3.0 * m.energy
    # one loud stretch of the stream can crowd out everything else — build the
    # shortlist round-robin across 30-min buckets so the editor judges the
    # whole stream's best, not one section's
    buckets: dict[int, list[Moment]] = {}
    for m in sorted(moments, key=lambda x: x.combined, reverse=True):
        buckets.setdefault(int(m.start // 1800), []).append(m)
    cand: list[Moment] = []
    while len(cand) < min(shortlist, len(moments)):
        added = False
        for b in sorted(buckets):
            if buckets[b] and len(cand) < shortlist:
                cand.append(buckets[b].pop(0))
                added = True
        if not added:
            break
    cand.sort(key=lambda x: x.combined, reverse=True)

    blocks = []
    for i, m in enumerate(cand, 1):
        a, b = m.start - 8, m.end + 8
        lines = _transcript_lines(
            [w for w in words if a <= w.start <= b], profile)
        snippet = "\n".join(f"[{int(t)}] {text}" for t, text in lines)
        blocks.append(
            f"CANDIDATE {i} | scorer said {m.score:.0f}/10: {m.title}\n"
            f"suggested {m.start:.0f}s -> {m.end:.0f}s | "
            f"measured loudness {m.energy:.2f}\n"
            f"transcript (8s lead-in/out included):\n{snippet}")
    body = "\n\n".join(blocks)

    data = None
    for name in [model] + [m for m in (fallback_models or []) if m != model]:
        try:
            data = _fn_for(name)(
                _client_provider(model, base_url, api_key_env)(name), name,
                body,
                EDITOR.format(
                    streamer=streamer,
                    persona=PERSONAS.get(persona, PERSONAS["generic"])
                    .format(streamer=streamer)),
                schema=RERANK_SCHEMA)
            break
        except Exception as e:
            log(f"  ! editor pass on {name} failed "
                f"({type(e).__name__}: {str(e)[:80]})")
    if data is None:
        log("  editor pass unavailable -> keeping scorer ranking")
        return moments

    keep: list[Moment] = []
    for c in data.get("clips", []):
        if not (1 <= int(c["id"]) <= len(cand)) or c["post_score"] < post_bar:
            continue
        m = cand[int(c["id"]) - 1]
        s, e = float(c["start"]), float(c["end"])
        if m.start - 10 <= s < e <= m.end + 10 and 8 <= e - s <= 35:
            m.start, m.end = s, e
            m.edited = True
        m.score = float(c["post_score"])
        if c.get("title"):
            m.title = c["title"]
        if c.get("hook"):
            m.hook = c["hook"]
        if c.get("reason"):
            m.reason = c["reason"]
        keep.append(m)
    log(f"  editor pass kept {len(keep)}/{len(cand)} candidates")
    if not keep:
        # nothing cleared the bar; ship the least-bad one rather than zero
        log("  editor kept nothing -> shipping top scorer candidate only")
        keep = [cand[0]]
    return keep


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


def _settle_end(m: Moment, profile: np.ndarray, words: list[Word],
                max_extra: float = 6.0, tail_pad: float = 2.0) -> None:
    """Extend the end until the reaction audibly settles, instead of a blind
    fixed pad — screams/laughter play out fully, then ~2s of air. Capped so a
    nonstop-loud stream can't drag the clip forever."""
    limit = min(m.end + max_extra, float(len(profile)))
    thresh = max(0.12, 0.45 * energy_score(profile, m.start, m.end))
    last_loud = m.end
    for t in range(int(m.end), int(limit)):
        if profile[t] >= thresh:
            last_loud = t + 1.0
    m.end = min(limit, last_loud + tail_pad)
    # never cut a word in half at the end
    for w in words:
        if w.start >= m.end:
            break
        if w.start < m.end < w.end:
            m.end = w.end + 0.3
            break
    # finish the utterance: the button is often a QUIET tag line right after
    # the scream ("...I did my job"), which energy settling can't see. Keep
    # appending words while the speech is continuous (no real pause), with a
    # small slack budget past the energy limit.
    last_end = 0.0
    for w in words:
        if w.end <= m.end:
            last_end = max(last_end, w.end)
            continue
        if w.start >= m.end + 0.6:
            break  # real pause -> utterance over
        if w.end > limit + 3.0:
            break  # slack budget spent; don't drag forever
        m.end = w.end + 0.3
        last_end = w.end


def keep_intervals(words: list[Word], start: float, end: float,
                   max_gap: float = 2.2, keep_air: float = 0.45
                   ) -> list[tuple[float, float]]:
    """Jump-cut plan for one clip: silences longer than max_gap shrink to a
    beat (keep_air), so the length budget goes to content instead of dead
    air. Comedic pauses (< max_gap) survive untouched. Returns absolute
    (start, end) intervals to KEEP; a single interval means no cuts."""
    ws = [w for w in words if w.end > start and w.start < end]
    if len(ws) < 2:
        return [(start, end)]
    ivals: list[tuple[float, float]] = []
    cursor = start
    for a, b in zip(ws, ws[1:]):
        gap = b.start - a.end
        if gap > max_gap:
            ivals.append((cursor, a.end + keep_air * 0.6))
            cursor = b.start - keep_air * 0.4
    ivals.append((cursor, end))
    return ivals


def remap_words(words: list[Word], ivals: list[tuple[float, float]]
                ) -> list[Word]:
    """Project words onto the compressed (post jump-cut) timeline, 0-based."""
    out: list[Word] = []
    elapsed = 0.0
    for s, e in ivals:
        for w in words:
            if w.end <= s or w.start >= e:
                continue
            out.append(Word(max(w.start, s) - s + elapsed,
                            min(w.end, e) - s + elapsed, w.text))
        elapsed += e - s
    return out


def _trim_head(m: Moment, words: list[Word], max_len: float) -> None:
    """Length budget comes out of the HEAD, never the ending — the punchline
    lives at the end; the start is expendable setup. Cuts land on utterance
    boundaries (word after a pause), and leading dead air goes first even
    when under budget."""
    # skip pure leading silence regardless of budget
    for w in words:
        if w.end > m.start:
            if w.start - m.start > 1.2:
                m.start = w.start - 0.4
            break
    if m.end - m.start <= max_len:
        return
    floor = m.end - max_len
    prev_end = 0.0
    start = floor  # worst case: blind trim (old behaviour)
    for w in words:
        if w.end <= floor:
            prev_end = w.end
            continue
        if w.start >= m.end:
            break
        # first utterance start at/after the floor = cleanest entry point
        if w.start >= floor and w.start - prev_end >= 0.5:
            start = max(floor, w.start - 0.2)
            break
        prev_end = w.end
    m.start = start


def _snap_start(m: Moment, words: list[Word], max_len: float) -> None:
    """Never open mid-word: include the straddled word fully when the length
    budget allows, otherwise start right after it."""
    for w in words:
        if w.start > m.start:
            break
        if w.start <= m.start < w.end:
            if m.end - w.start <= max_len:
                m.start = max(0.0, w.start - 0.15)
            else:
                m.start = w.end
            break


def select_clips(moments: list[Moment], profile: np.ndarray, count: int,
                 min_len: float, max_len: float,
                 words: list[Word] | None = None,
                 min_gap_s: float = 0.0) -> list[Moment]:
    """Rank by LLM score + loudness, enforce length bounds and no overlap."""
    words = words or []
    for m in moments:
        # editor-tightened ends are deliberate cuts after the peak — give them
        # only a whisper of settle room, not a full extension
        if m.edited:
            _settle_end(m, profile, words, max_extra=1.5, tail_pad=0.5)
        else:
            _settle_end(m, profile, words)
        # over budget: trim dead air at the head — NEVER the ending. The
        # reaction/reveal lives at the end; the start is expendable setup.
        _trim_head(m, words, max_len)
        _snap_start(m, words, max_len)
        if m.end - m.start < min_len:
            m.start = max(0.0, m.end - min_len)  # more setup; ending stays put
            if m.end - m.start < min_len:
                m.end = m.start + min_len
        m.energy = energy_score(profile, m.start, m.end)
        m.combined = m.score + 3.0 * m.energy  # loudness = streamer, not NPC

    # near-silent "moments" are usually game dialogue the LLM mistook for content
    moments = [m for m in moments if m.energy >= 0.12]

    # two passes: first demand time spread (a batch of three clips from the
    # same 10 minutes is one clip posted thrice), then fill remaining slots
    # from whatever's left if spread alone can't reach count
    picked: list[Moment] = []
    ranked = sorted(moments, key=lambda x: x.combined, reverse=True)
    for gap in (min_gap_s, 0.0):
        for m in ranked:
            if m in picked or any(
                    not (m.end + gap <= p.start or m.start >= p.end + gap)
                    for p in picked):
                continue
            picked.append(m)
            if len(picked) == count:
                break
        if len(picked) == count:
            break
    return sorted(picked, key=lambda m: m.start)
