"""Pick the funniest moments: Claude scores the transcript, loudness breaks ties."""

import json
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import usage
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
                    "archetype": {"type": "string", "enum": [
                        "banter_roast", "soundbite", "bit_commitment",
                        "stinger", "wholesome", "rage_arc",
                        "coincidence_verbal", "physical_fail",
                        "destructive_rage", "irl_reveal",
                        "clutch_needs_replay", "other"]},
                    "trigger_quote": {"type": "string"},
                    "button_quote": {"type": "string"},
                    "button_kind": {"type": "string", "enum": [
                        "speech", "scream", "visual", "game_sound"]},
                    "trigger_role": {"type": "string", "enum": [
                        "streamer", "chat", "game", "npc", "video", "other"]},
                    "button_role": {"type": "string", "enum": [
                        "streamer", "game", "npc", "video", "other"]},
                    "self_contained": {"type": "boolean"},
                    "has_button": {"type": "boolean"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "score": {"type": "integer"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                },
                "required": ["reason", "archetype", "trigger_quote",
                             "button_quote", "button_kind", "trigger_role",
                             "button_role", "self_contained", "has_button",
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
flop — "JYNXZI scores a POWER SHOT" (same game!) got 26 views. Name JYNXZI
and make the competitive stakes specific, but follow PACKAGING MODE on whether
the outcome must stay hidden.""",
    "generic": """{streamer} is a gaming streamer. Viewers clip: big comedic
reactions, rage moments, absurd one-liners, chat interactions, screaming fits,
unexpected jokes, self-roasts, game fails with big verbal reactions.""",
}

TITLE_PACKAGING = {
    "curiosity": """PACKAGING MODE — CURIOSITY GAP:
- Open ONE unanswered question in the title and on-screen hook.
- Withhold the payoff. Never summarize "X happens, then Y happens" and never
  quote the button/punchline.
- Promise the tension honestly; the viewer should need the clip to resolve it.
Example shape: "CaseOh realized the crowd saw everything…".""",
    "stakes": """PACKAGING MODE — STAKES FIRST:
- Lead with the goal, constraint, or consequence before the attempt.
- Do not reveal whether it succeeds or quote the final reaction.
- Prefer a specific stake over generic words like crazy or hilarious.
Example shape: "CaseOh had one chance to save him".""",
    "reaction": """PACKAGING MODE — REACTION TEASE:
- Promise an unusual or contradictory reaction.
- Conceal either the exact trigger or punchline so an open loop remains.
- Never claim screaming or panic unless the audio evidence proves it.
- Ground the title in one CONCRETE odd detail, action, goal, or contradiction
  from the setup. The title should create a specific question, not merely
  "what happened?"
- BAN adjective-slot templates: "X's UNHINGED reaction to this", "X was NOT
  ready for this", "X LOST IT during this", "X's UNEXPECTED logic", and
  generic "reaction/incident/moment" wording. Those summarize emotion without
  giving the viewer a reason to care.
- Use natural capitalization; do not shout a random adjective in ALL CAPS.
Example shape: "The bathroom had a window in the worst place".""",
    "quote": """PACKAGING MODE — SETUP QUOTE:
- Build the title from a short provocative fragment of the trigger/setup.
- Never use the button or punchline as the quote.
- Add only enough framing to make the setup legible; keep the answer hidden.
Example shape: "“You all just witnessed that…”".""",
}


def title_packaging(strategy: str) -> str:
    return TITLE_PACKAGING.get(strategy, TITLE_PACKAGING["curiosity"])


SYSTEM = """You are the lead editor of a Twitch highlights Shorts channel. You
find moments a professional clip editor would cut into a standalone 15-28s
YouTube Short. You are ruthless: most of any stream is NOT clip-worthy, and a
mediocre pick wastes an upload slot.

{persona}

{packaging}

You get transcript lines as `[seconds] text`. Delivery tags measured from the
actual audio: [SCREAM]/[loud] = volume, [rapid] = excited fast speech,
`[pause Ns]` between lines = N seconds of silence (a pause right after a peak
is a comedic beat and a clean out-point; long pauses are dead air the render
will jump-cut). `[chat exploding: N msgs/5s]` = the live Twitch chat spiked
at that moment — strong evidence the crowd saw something clip-worthy; look
for what triggered it just BEFORE the spike (chat lags the moment by a few
seconds). Untagged lines were spoken at normal volume. Rules:
- write `reason` FIRST (2-3 sentences), then PROVE you understood the moment:
  `trigger_quote` = the exact transcript words of the thing that CAUSES the
  reaction; `button_quote` = the exact words of the payoff/tag. If you cannot
  quote a real trigger from the transcript, the moment does not qualify —
  no quote, no clip
- `archetype`: classify the moment. AUTO-REJECT (do not return) archetypes
  whose payoff our format cannot show — physical_fail (the fall/crash is
  outside the facecam crop), destructive_rage (needs the wide shot),
  irl_reveal (second person off-frame), clutch_needs_replay (stakes need a
  killcam). Favor: banter_roast, soundbite, bit_commitment, rage_arc,
  coincidence_verbal, wholesome, stinger
- a `[viewers asked to clip this]` tag is a HINT with limited authority:
  streamers also say "clip it" to save bugs or reports for later review.
  The moment must still earn its place through trigger/button/archetype
- self_contained: true only if it lands with ZERO outside context. A moment
  needing anything from 10 minutes earlier fails, no matter how funny
- has_button: true if the clip ends on a payoff (tag joke, reveal, reaction
  line) rather than trailing off after the peak
- label the evidence: button_kind is speech, scream, visual, or game_sound;
  trigger_role and button_role identify who/what owns each beat. A game/NPC/
  video button is not a streamer Short and must not be returned
- score 1-10, calibrated against the WHOLE multi-hour stream, not this chunk:
  10 = the best moment of the entire stream, 8-9 = elite (most chunks have
  NONE), 6-7 = solid, 5 = borderline. Skip anything under 5. Never inflate —
  a boring chunk should return zero or low-scored moments
- delivery check, both directions: a "rage/screaming" claim REQUIRES
  [SCREAM]/[loud] tags at its peak — but the reverse is NOT true: loud does
  not mean funny. [SCREAM] tags fire on ANY audio peak, including GAME
  volume (explosions, in-game voices, music). The transcript content must
  prove the humor on its own; loudness only corroborates delivery
- CRITICAL: the transcript mixes the STREAMER's voice with in-game dialogue
  (NPCs, cutscenes, videos on screen). Only the streamer's own reactions count —
  loud, first-person, addressed to chat or the game. NEVER pick a moment whose
  highlight is a game character's line; game dialogue can only be setup for the
  streamer's reaction
- start/end in seconds. THE SETUP IS MANDATORY: the clip must contain the
  thing that CAUSES the reaction (the game event, the chat message being
  read, the question, the mistake). A reaction whose trigger is off-screen
  is noise, not a joke — if you can't include the trigger, don't pick the
  moment. Viewers must understand WHY he's screaming
- moments must be 18-32 seconds: enough for trigger -> reaction -> button,
  but TIGHT — a Short that drags loses viewers. Aim 20-28. Trim dead air
  inside via late start, not by amputating the setup. NEVER cut the ending short: the reaction must fully play out.
  End 2-3 seconds AFTER the reaction settles, not mid-reaction.
  If the moment involves a guess, answer, or reveal (word games, quizzes,
  "wait is it X?"), the clip MUST include the reveal and the reaction to it —
  never end during the guessing
- title: follow PACKAGING MODE. Max 72 characters, concrete, no clickbait
  lies, no generic "funny moment" language, and do not reveal the button
- hook: a short on-screen overlay line (3-8 words, sentence case) that teases the
  moment without spoiling the punchline. It must create a reason to watch the
  next beat, not summarize what viewers already see. Wrap exactly ONE
  emotional keyword in *asterisks* — it gets rendered in color.
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
                    "trigger_quote": {"type": "string"},
                    "button_quote": {"type": "string"},
                    "button_kind": {"type": "string", "enum": [
                        "speech", "scream", "visual", "game_sound"]},
                    "trigger_role": {"type": "string", "enum": [
                        "streamer", "chat", "game", "npc", "video", "other"]},
                    "button_role": {"type": "string", "enum": [
                        "streamer", "game", "npc", "video", "other"]},
                    "archetype": {"type": "string"},
                    "decision": {"type": "string", "enum": [
                        "post", "bench", "reject"]},
                    "reject_reason": {"type": "string"},
                },
                "required": ["id", "post_score", "start", "end",
                             "title", "hook", "reason",
                             "trigger_quote", "button_quote", "button_kind",
                             "trigger_role", "button_role", "archetype",
                             "decision", "reject_reason"],
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

{packaging}

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
SETUP CHECK: with the 90s lead-in you can see what caused the reaction. If
the suggested bounds start AFTER the trigger, widen start to include it — a
context-free scream is an automatic cut, no matter how loud. When the trigger
is the streamer READING something (a chat message, a video title, an on-screen
line), the clip MUST open on him reading/reacting to it — start on the read,
never mid-reaction. The viewer has to see WHAT he saw before he reacts, or the
clip makes no sense.
For every keep, `trigger_quote` and `button_quote` must be VERBATIM words
from the transcript INSIDE your returned bounds (the cause and the payoff).
These are machine-checked downstream — but do NOT cut candidates just
because quoting is hard; keep 5-6 candidates whenever the material allows
(the bench matters: downstream checks pick the best). For nonverbal payoffs
(pure scream) quote the last intelligible line before it.
Return EVERY candidate exactly once, ordered best to worst. Mark each as
`post`, `bench`, or `reject`; downstream deterministic gates use the bench to
replace a failed post candidate. Give a concrete reject_reason for rejects.
Label button_kind, trigger_role, and button_role. A game/NPC/video may be the
trigger, but only the streamer's own speech or scream can be the button.
Also return tightened start/end as ABSOLUTE stream seconds — transcript lines
carry [seconds] markers; anchor your cuts to them, never to offsets within the
snippet. Stay within 20s of the suggestion, 18-45s long, peak in the final
third. A dense 38-45s story is better than an abrupt 20s fragment; reject or
cut dead time, not useful setup/escalation. Return a new title + hook for every
kept clip, following PACKAGING
MODE. The title is packaging, not a plot synopsis: never state both cause and
resolution, never use "then" to walk through the sequence, and never reveal
the quoted button. The hook is 3-8 words, sentence case, exactly ONE emotional
keyword wrapped in *asterisks*. It must open a loop in the first seconds, not
describe the entire clip.
Candidates come from two sources and you are the arbiter: some were clipped
live by viewers (tagged [CROWD GROUND TRUTH: N viewers clipped this]), the
rest were found by scoring the transcript. Judge purely on which makes the
better standalone Short — a moment with no crowd tag CAN and SHOULD outrank
a crowd-tagged one when it has the stronger trigger/payoff arc.
Candidates tagged [CROWD GROUND TRUTH] carry a strong human prior: do not
overrule them on taste alone ("not that funny" is NOT a valid cut). But they are NOT infallible for OUR format — viewers often
clip for visual gags a captions+facecam short cannot show. CUT a crowd
candidate when the transcript shows its payoff won't survive our format:
the humor is a game visual/NPC line with no real streamer reaction beyond
one word, the payoff is off-camera, or a second person carries it. When you
KEEP a crowd candidate, your job is boundaries/title/hook: make sure the
FULL arc is inside the bounds — if the transcript shows the story resolving
after the suggested end, EXTEND the end to the resolution (up to 45s total).
A crowd moment with almost no dialogue but a real streamer reaction is a
STINGER — keep it tight (18-25s) and let the reaction carry it.
Be ruthless with everything else: returning ZERO non-crowd keeps is valid."""


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
    crowd: int = 0        # distinct humans who clipped this live (ground truth)
    crowd_anchor: float = 0.0  # local mode of Twitch clip START timestamps
    crowd_peak: float = 0.0  # deprecated cache field; never treated as payoff
    source: str = ""      # provenance: "crowd" (viewer clips) or "ai" (LLM)
    trigger_quote: str = ""  # editor's quoted cause — must appear in the clip
    button_quote: str = ""   # editor's quoted payoff — must appear in the clip
    protect_start: float = -1.0  # trigger start _trim_head must not cross
    archetype: str = "other"
    button_kind: str = "speech"
    trigger_role: str = "unknown"
    button_role: str = "streamer"
    decision: str = "bench"
    reject_reason: str = ""


def _transcript_lines(words: list[Word],
                      profile: np.ndarray | None = None) -> list[tuple[float, str]]:
    """Group words into ~8s lines: (start_time, text). With a loudness profile,
    lines are tagged [SCREAM]/[loud] so a text-only model can hear delivery —
    without this it can't tell a genuine meltdown from a muttered one-liner."""
    lines, cur, cur_start = [], [], None
    # RELATIVE loudness: thresholds float on the streamer's own rolling
    # baseline instead of absolute dB. A permanently-loud streamer (CaseOh)
    # doesn't read as all-SCREAM, and quiet streamers' genuine peaks aren't
    # invisible. Game-audio false positives drop with it.
    base = None
    if profile is not None and len(profile):
        nz = profile[profile > 0.03]
        base = float(np.median(nz)) if len(nz) else 0.2

    def _flush(start: float, end: float) -> None:
        text = " ".join(cur)
        dur = max(end - start, 0.5)
        if len(cur) / dur >= 4.2:  # excited fast talk — free excitement signal
            text = "[rapid] " + text
        # repetition escalation: same word looped = rage/hype arc marker
        toks = [t.lower().strip(".,!?") for t in cur]
        for t in set(toks):
            if len(t) > 1 and toks.count(t) >= 4:
                text = f"[repeat x{toks.count(t)}] " + text
                break
        if base is not None:
            # local baseline: this 10-min neighbourhood of the stream
            lo, hi = max(0, int(start) - 300), int(end) + 300
            seg = profile[lo:hi]
            nz = seg[seg > 0.03]
            b = float(np.median(nz)) if len(nz) else base
            peak = float(profile[int(start):int(end) + 1].max(initial=0.0))
            if peak >= max(0.50, 2.0 * b):
                text = "[SCREAM] " + text
            elif peak >= max(0.32, 1.45 * b):
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


_LAUGH_EMOTES = ("kekw", "lul", "omegalul", "lmao", "lmfao", "😂", "🤣",
                 "haha", "icant", "dead")
_CALLOUT_RE = None  # compiled lazily


def _chat_signal_lines(chat: dict | None) -> list[tuple[float, str]]:
    """Chat -> pseudo-transcript lines. Three signals, weakest to strongest:
    density spikes (volume only — sarcasm-poisoned), laugh-emote bursts
    (semantics beat raw rate, EMNLP'17), and 'clip that' callouts. Callouts
    are deliberately power-capped: a HINT tag only — streamers also say
    'clip it' to save bugs/reports for review, so the rubric still decides."""
    if not chat:
        return []
    lines: list[tuple[float, str]] = []

    density = chat.get("density") or []
    if density:
        rates = np.array([r for _, r in density])
        thresh = max(rates.mean() + 2.0 * rates.std(), 1.5)
        prev = -1e9
        for (t, r) in density:
            if r >= thresh and t - prev >= 60:
                lines.append((t, f"[chat exploding: {r:.0f} msgs/s]"))
                prev = t

    texts = chat.get("texts") or []
    if texts:
        import re as _re
        global _CALLOUT_RE
        if _CALLOUT_RE is None:
            _CALLOUT_RE = _re.compile(
                r"\b(clip (that|it|this)|someone clip|clip pls|clipper?s\b)",
                _re.IGNORECASE)
        # laugh-emote bursts per 10s bucket
        buckets: dict[int, int] = {}
        for t, msg in texts:
            m = msg.lower()
            if any(e in m for e in _LAUGH_EMOTES):
                buckets[int(t // 10)] = buckets.get(int(t // 10), 0) + 1
        if buckets:
            vals = np.array(list(buckets.values()))
            bthresh = max(float(vals.mean() + 2.0 * vals.std()), 4.0)
            prev = -1e9
            for b in sorted(buckets):
                if buckets[b] >= bthresh and b * 10 - prev >= 60:
                    lines.append((float(b * 10),
                                  f"[chat spamming laugh emotes x{buckets[b]}]"))
                    prev = b * 10
        # callouts: cap at the 6 earliest per stream so a spammy chat can't
        # flood the transcript with fake importance
        seen = 0
        prev = -1e9
        for t, msg in texts:
            if _CALLOUT_RE.search(msg) and t - prev >= 90:
                lines.append((t, "[viewers asked to clip this — hint only: "
                                 "verify the moment itself is worth it]"))
                prev = t
                seen += 1
                if seen >= 6:
                    break
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
    usage.record_response(model, resp)
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
    # "claude-code" = CLI default model; "claude-code:opus" etc. pins one.
    # Prompt goes via STDIN: editor-pass prompts are big enough to break as
    # an argv argument, and stdin is the CLI's supported piping path.
    cmd = [_claude_cli() or "claude", "-p"]
    if ":" in model:
        cmd += ["--model", model.split(":", 1)[1]]
    last_err = ""
    for attempt in (1, 2):
        r = subprocess.run(cmd, input=prompt, capture_output=True,
                           text=True, timeout=600)
        if "Not logged in" in r.stdout:
            raise RuntimeError(
                "claude CLI not logged in — run `claude` in a terminal, type "
                "/login, choose your Claude subscription account")
        if r.returncode == 0:
            # The CLI runs on the founder's Claude subscription and reports no
            # usage block. Count the call so the dashboard shows "N calls,
            # tokens unknown" rather than an unexplained $0.
            usage.record_call(model)
            return _extract_json(r.stdout)
        last_err = (r.stderr.strip() or r.stdout.strip())[-500:]
    raise RuntimeError(f"claude CLI failed after 2 tries: {last_err}")


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
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(**kw)
                # Recorded here, not at the return sites: a response whose
                # json_schema body we then reject was still billed, and the
                # founder's cost page has to show tokens actually paid for.
                usage.record_response(kw.get("model") or model, resp)
                return resp
            except Exception as e:
                msg = str(e).lower()
                # Daily/account quota exhaustion does not improve by sleeping;
                # fail over immediately. Only transient rate pressure backs
                # off, and the whole fallback chain stays under two minutes.
                permanent = any(x in msg for x in (
                    "current quota", "quota exceeded", "per day",
                    "billing details", "session limit"))
                if ("429" in msg or "rate" in msg) and not permanent:
                    _time.sleep(15 * (attempt + 1))
                    continue
                raise
        raise RuntimeError("rate-limited after 3 retries")

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
                       api_key=os.environ[api_key_env or "OPENAI_API_KEY"],
                       timeout=60.0, max_retries=0)
        elif name.startswith("gemini"):
            c = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                       api_key=os.environ["GEMINI_API_KEY"],
                       timeout=60.0, max_retries=0)
        elif _is_openai(name):
            c = OpenAI(timeout=60.0, max_retries=0)
        else:  # llama/qwen/etc -> Groq
            c = OpenAI(base_url="https://api.groq.com/openai/v1",
                       api_key=os.environ["GROQ_API_KEY"],
                       timeout=60.0, max_retries=0)
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
                   chat: list[tuple[float, str]] | None = None,
                   title_strategy: str = "curiosity",
                   ) -> list[Moment]:
    _models = [model] + [m for m in (fallback_models or []) if m != model]
    persona_txt = PERSONAS.get(persona, PERSONAS["generic"]).format(
        streamer=streamer)
    system = SYSTEM.format(
        persona=persona_txt, packaging=title_packaging(title_strategy))
    _client_for = _client_provider(model, base_url, api_key_env)

    lines = sorted(_transcript_lines(words, profile)
                   + _chat_signal_lines(chat), key=lambda x: x[0])
    chunk_s = chunk_minutes * 60

    # split lines into time chunks
    chunks: list[list[tuple[float, str]]] = []
    cur, cur_t0 = [], 0.0
    for t, text in lines:
        if t - cur_t0 >= chunk_s and cur:
            chunks.append(cur)
            # 75s of overlap: a bit building across the boundary is visible
            # in full to at least one chunk
            cur = [(tt, tx) for tt, tx in cur if tt >= t - 75]
            cur_t0 = t
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
            if m.get("archetype") in ("physical_fail", "destructive_rage",
                                      "irl_reveal", "clutch_needs_replay"):
                continue  # payoff structurally outside captions+facecam
            if m["score"] >= 5 and m["end"] > m["start"]:
                moments.append(Moment(
                    start=float(m["start"]), end=float(m["end"]),
                    score=float(m["score"]), title=m["title"],
                    hook=m.get("hook", ""), reason=m.get("reason", ""),
                    archetype=m.get("archetype", "other"),
                    trigger_quote=m.get("trigger_quote", ""),
                    button_quote=m.get("button_quote", ""),
                    button_kind=m.get("button_kind", "speech"),
                    trigger_role=m.get("trigger_role", "unknown"),
                    button_role=m.get("button_role", "streamer"),
                ))
    return moments


SMARTCUT_SCHEMA = {
    "type": "object",
    "properties": {
        "keep": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"start": {"type": "number"},
                               "end": {"type": "number"}},
                "required": ["start", "end"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["keep"],
    "additionalProperties": False,
}

SMARTCUT_SYS = """You tighten a Twitch clip into a punchy YouTube Short by
CUTTING redundant talking — not just silence. You get the clip's transcript
with [seconds] timestamps. Keep the essential arc and nothing else:
- the TRIGGER (the thing that causes the reaction — a read message, a game
  event, a question),
- the strongest REACTION,
- the BUTTON (the payoff / punchline at the end).
CUT: repeated phrases, restarts, rambling, filler, dead tangents, him saying
the same thing three times. A viewer should hear cause -> reaction -> payoff
with no dead weight.

Return KEEP spans as absolute [start, end] second-ranges taken from the
[seconds] markers. Everything outside the spans is removed and the kept
pieces play back-to-back. Rules:
- cut on phrase boundaries (right after a word / before the next), never
  mid-word — read the timestamps and land cuts in the gaps between words.
- ALWAYS keep the trigger span and the button span in full. These are given:
  TRIGGER = "{trigger}"  BUTTON = "{button}".
- aim for a total kept length near {target} seconds — DON'T over-cut into a
  choppy 10-second blur; keep the natural flow of the bit, just remove the
  clearly redundant parts. Prefer fewer, longer spans over many tiny slivers.
- if nothing is redundant, return a single span covering the whole clip."""


def smart_cut(words: list[Word], start: float, end: float,
              trigger_quote: str, button_quote: str, target: float,
              model: str, base_url: str | None = None,
              api_key_env: str | None = None,
              fallback_models: list[str] | None = None,
              log=print) -> list[tuple[float, float]] | None:
    """LLM condense: cut REDUNDANT TALKING (not just silence) to keep a
    talking-dense clip's trigger->reaction->payoff arc tight. Returns
    absolute KEEP intervals, or None (caller falls back to silence cuts)
    when the model is unavailable or its plan can't be trusted (drops the
    button, reorders time, over-cuts). Only meant for clips the silence
    jump-cut couldn't get under budget."""
    clip_ws = [w for w in words if start <= w.start <= end]
    if len(clip_ws) < 8:
        return None
    body = "\n".join(f"[{w.start:.1f}] {w.text}" for w in clip_ws)
    sysmsg = SMARTCUT_SYS.format(trigger=trigger_quote[:80],
                                 button=button_quote[:80], target=int(target))
    data = None
    for name in [model] + [m for m in (fallback_models or []) if m != model]:
        try:
            data = _fn_for(name)(
                _client_provider(model, base_url, api_key_env)(name), name,
                body, sysmsg, schema=SMARTCUT_SCHEMA)
            break
        except Exception as e:
            log(f"  ! smart-cut on {name} failed ({type(e).__name__})")
    if not data or not data.get("keep"):
        return None

    # validate: in-bounds, chronological, non-trivial, and both evidence
    # endpoints survive. An LLM cut is a proposal, never its own verifier.
    spans = []
    for k in data["keep"]:
        s, e = float(k["start"]), float(k["end"])
        s, e = max(s, start), min(e, end)
        if e - s >= 0.4:
            spans.append((s, e))
    spans.sort()
    if not spans:
        return None
    # merge tiny gaps so ffmpeg isn't cutting on sub-0.3s slivers
    merged = [spans[0]]
    for s, e in spans[1:]:
        if s - merged[-1][1] <= 0.4:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    total = sum(e - s for s, e in merged)
    if total < 6 or total > (end - start):
        return None
    # the button/payoff MUST be inside the kept spans, or we shipped a clip
    # with no punchline — reject and fall back
    kept_text = " ".join(w.text.lower() for w in clip_ws
                         if any(s <= w.start <= e for s, e in merged))
    ttoks = [t for t in re.sub(r"[^a-z0-9 ]", " ", trigger_quote.lower()).split()
             if len(t) > 3]
    btoks = [t for t in re.sub(r"[^a-z0-9 ]", " ", button_quote.lower()).split()
             if len(t) > 3]
    if ttoks and sum(1 for t in set(ttoks) if t in kept_text) < 0.5 * len(set(ttoks)):
        log("  smart-cut dropped the trigger -> fallback to silence cuts")
        return None
    if btoks and sum(1 for t in set(btoks) if t in kept_text) < 0.5 * len(set(btoks)):
        log("  smart-cut dropped the button -> fallback to silence cuts")
        return None
    log(f"  smart-cut: {end - start:.0f}s -> {total:.0f}s "
        f"({len(merged)} kept span(s))")
    return merged


def rerank_moments(moments: list[Moment], words: list[Word],
                   profile: np.ndarray, model: str, log=print,
                   base_url: str | None = None,
                   api_key_env: str | None = None,
                   streamer: str = "the streamer",
                   fallback_models: list[str] | None = None,
                   shortlist: int = 15, post_bar: int = 7,
                   persona: str = "generic",
                   cache_dir: Path | None = None,
                   title_strategy: str = "curiosity",
                   desired_count: int = 3) -> list[Moment]:
    """Editor pass: chunk scoring grades on a curve (every chunk hands out
    10s), so the shortlist gets re-judged head-to-head in ONE call, with the
    measured loudness and full transcript context the chunk scorer never saw.
    Only candidates clearing the posting bar survive; boundaries/titles/hooks
    come back tightened."""
    if not moments:
        return []
    # a clip window must contain actual speech — hallucinated timestamps and
    # music-only stretches have none, no matter how loud they measured
    starts = np.array([w.start for w in words])
    moments = [m for m in moments if m.crowd > 0 or
               np.searchsorted(starts, m.end) - np.searchsorted(starts, m.start) >= 8]
    if not moments:
        return []
    for m in moments:
        m.energy = energy_score(profile, m.start, m.end)
        # energy is a plausibility check, NOT a ranking force — loud game
        # audio is not humor. Comedy score dominates; mild energy tiebreak.
        m.combined = m.score + 0.75 * m.energy
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
        a, b = m.start - 90, m.end + 45  # setup lives BEFORE the pick
        lines = _transcript_lines(
            [w for w in words if a <= w.start <= b], profile)
        snippet = "\n".join(f"[{int(t)}] {text}" for t, text in lines)
        blocks.append(
            f"CANDIDATE {i} | scorer said {m.score:.0f}/10: {m.title}\n"
            + (f"[CROWD GROUND TRUTH: {m.crowd} separate viewers clipped this "
               f"moment live]\n" if m.crowd else "")
            + f"suggested {m.start:.0f}s -> {m.end:.0f}s | "
            + f"measured loudness {m.energy:.2f}\n"
            + "transcript (90s lead-in / 45s tail included — judge whether "
            + f"the\n  setup is inside the suggested bounds):\n{snippet}")
    body = "\n\n".join(blocks)

    sysmsg = EDITOR.format(
        streamer=streamer,
        packaging=title_packaging(title_strategy),
        persona=PERSONAS.get(persona, PERSONAS["generic"])
        .format(streamer=streamer))
    desired_count = max(1, int(desired_count))
    inventory_target = min(len(cand), desired_count + max(3, desired_count // 2))
    sysmsg += f"""

BATCH SIZE: The user requested {desired_count} finished clips. Build a truthful
replacement bench of about {inventory_target} post/bench candidates when the
material genuinely supports it, because deterministic arc and media checks may
still remove some. Search each supplied transcript for tighter alternative
bounds before rejecting it. Never invent quotes, retain filler, or lower the
story/retention bar merely to hit the number."""
    data = None
    cache_file = None
    if cache_dir is not None:
        key = hashlib.sha256(
            (model + "\0" + sysmsg + "\0" + body).encode()).hexdigest()[:20]
        cache_file = Path(cache_dir) / f"editor-{key}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                log(f"  editor judgment cache: {cache_file.name}")
            except Exception:
                data = None
    for name in [model] + [m for m in (fallback_models or []) if m != model]:
        if data is not None:
            break
        try:
            data = _fn_for(name)(
                _client_provider(model, base_url, api_key_env)(name), name,
                body, sysmsg,
                schema=RERANK_SCHEMA)
            if cache_file is not None:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                tmp = cache_file.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, indent=2))
                tmp.replace(cache_file)
            break
        except Exception as e:
            log(f"  ! editor pass on {name} failed "
                f"({type(e).__name__}: {str(e)[:80]})")
    if data is None:
        log("  editor pass unavailable -> keeping scorer ranking")
        return moments

    keep: list[Moment] = []
    seen: set[int] = set()
    for c in data.get("clips", []):
        if not (1 <= int(c["id"]) <= len(cand)) or int(c["id"]) in seen:
            continue
        seen.add(int(c["id"]))
        m = cand[int(c["id"]) - 1]
        s, e = float(c["start"]), float(c["end"])
        lo, hi = (m.start - 90, m.end + 40) if m.crowd else (m.start - 25,
                                                              m.end + 15)
        # Twitch vod_offset is the published clip START, not the button press
        # or payoff. It may guide a context window but must never force a cut.
        if m.crowd:
            n_words = sum(1 for w in words if m.start <= w.start <= m.end)
            if n_words < 15:  # stinger: crowd bounds verbatim, title only
                if lo <= s < e <= hi and 8 <= e - s <= 32:
                    m.start, m.end = s, e
            else:
                if lo <= s < e <= hi and 14 <= e - s <= 45:
                    m.start, m.end = s, e
                m.edited = True
        elif lo <= s < e <= hi and 14 <= e - s <= 45:
            m.start, m.end = s, e
            m.edited = True
        m.score = float(c["post_score"])
        m.trigger_quote = c.get("trigger_quote", "")
        m.button_quote = c.get("button_quote", "")
        m.button_kind = c.get("button_kind", "speech")
        m.trigger_role = c.get("trigger_role", "unknown")
        m.button_role = c.get("button_role", "streamer")
        m.archetype = c.get("archetype", m.archetype)
        m.decision = c.get(
            "decision", "post" if m.score >= post_bar else "bench")
        m.reject_reason = c.get("reject_reason", "")
        # TRIGGER PULLBACK: if the trigger phrase also occurs BEFORE the
        # chosen start (streamer echoing a donation/message read earlier),
        # open on the ORIGINAL read so the viewer sees the cause. Safe now
        # that select_clips is jump-cut-aware — the dead gap between the read
        # and his reaction gets compressed, keeping the clip tight.
        import re as _re
        tqt = [t for t in _re.sub(r"[^a-z0-9 ]", " ",
                                  m.trigger_quote.lower()).split() if len(t) > 3]
        if tqt:
            need = 0.6 * len(set(tqt))
            for w in words:
                if w.start >= m.start - 3:
                    break
                if w.start < m.start - 45:
                    continue
                near = " ".join(x.text.lower() for x in words
                                if w.start <= x.start <= w.start + 6)
                if sum(1 for t in set(tqt) if t in near) >= need:
                    m.start = max(0.0, w.start - 1.0)
                    m.edited = True
                    break
        if c.get("title"):
            m.title = c["title"]
        if c.get("hook"):
            m.hook = c["hook"]
        if c.get("reason"):
            m.reason = c["reason"]
        keep.append(m)
    # Schema-compliant models should return every candidate. Retain omissions
    # as low-priority bench entries so a transient model omission cannot
    # destroy the replacement pool.
    for i, m in enumerate(cand, 1):
        if i not in seen:
            m.decision = "bench"
            m.reject_reason = "editor omitted candidate"
            keep.append(m)
    judged_ids = {id(m) for m in cand}
    for m in moments:
        if id(m) not in judged_ids:
            m.decision = "bench"
            m.reject_reason = "below editor shortlist"
            keep.append(m)
    keep.sort(key=lambda m: (
        {"post": 0, "bench": 1, "reject": 2}.get(m.decision, 1),
        -m.score, -m.combined))
    log(f"  editor scored {len(keep)}/{len(cand)} candidates "
        f"({sum(m.decision == 'post' for m in keep)} post-ready)")
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
                   max_gap: float = 3.5, keep_air: float = 0.45,
                   profile: np.ndarray | None = None
                   ) -> list[tuple[float, float]]:
    """Jump-cut plan for one clip: dead air LONGER than max_gap shrinks to a
    beat (keep_air). DURATION is the real signal — measured on real clips,
    quiet NPC sounds/jumpscares are loudness-identical to silence (both mean
    ~0.03); what separates a payoff sound (2-3s gap) from dead air (a 9s
    gap) is length. So short gaps are always kept (NPC sounds, comedic beats
    live there); only long gaps are cut, and even then not if they're
    genuinely LOUD (a real scream/effect). Returns absolute (start, end)
    intervals to KEEP; one interval means no cuts."""
    ws = [w for w in words if w.end > start and w.start < end]
    if len(ws) < 2:
        return [(start, end)]

    def _keep_gap(a_end: float, b_start: float) -> bool:
        # gap <= max_gap: always keep (short sounds / comedic beats).
        # max_gap < gap <= 6s: keep only a genuinely LOUD sustained event
        # (a scream/effect between words). gap > 6s: ALWAYS cut — no payoff
        # sound lasts 6s+; a long no-speech stretch is dead air even when
        # loud game music plays under it (that's what left a 26s gap in a
        # clip). Duration overrides loudness past 6s.
        gap = b_start - a_end
        if gap <= max_gap:
            return True
        if gap > 6.0:
            return False
        if profile is None or not len(profile):
            return False
        seg = profile[int(a_end):int(b_start) + 1]
        return bool(len(seg) and float(seg.max()) >= 0.45)

    ivals: list[tuple[float, float]] = []
    cursor = start
    for a, b in zip(ws, ws[1:]):
        if not _keep_gap(a.end, b.start):
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


def _trim_head(m: Moment, words: list[Word], max_len: float,
               protect: float | None = None) -> None:
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
    if protect is not None and protect < floor:
        floor = protect  # keep the trigger/setup even if it runs long
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
                 min_gap_s: float = 0.0,
                 raw_profile: np.ndarray | None = None) -> list[Moment]:
    """Rank by LLM score + loudness, enforce length bounds and no overlap."""
    words = words or []
    for m in moments:
        # editor-tightened ends are deliberate cuts after the peak — give them
        # only a whisper of settle room, not a full extension
        if m.edited:
            _settle_end(m, profile, words, max_extra=1.5, tail_pad=0.5)
        else:
            _settle_end(m, profile, words)
        # length control is JUMP-CUT AWARE. Crowd moments carry an intentional
        # trigger->payoff arc (possibly a pulled-back donation read) — NEVER
        # head-trim them here; the render's silence-cut + smart-cut condense
        # them to length while keeping the setup. Non-crowd clips trim as
        # usual when even silence removal leaves them over budget.
        eff = m.end - m.start
        if raw_profile is not None:
            eff = sum(e - s for s, e in
                      keep_intervals(words, m.start, m.end, profile=raw_profile))
        if not m.crowd and eff > max_len:
            _trim_head(m, words, max_len)
        _snap_start(m, words, 1e9 if (m.crowd or eff <= max_len) else max_len)
        if m.end - m.start < min_len:
            m.start = max(0.0, m.end - min_len)  # more setup; ending stays put
            if m.end - m.start < min_len:
                m.end = m.start + min_len
        m.energy = energy_score(profile, m.start, m.end)
        m.combined = m.score + 0.75 * m.energy  # comedy ranks, loudness tiebreaks

    # near-silent "moments" are usually game dialogue the LLM mistook for content
    moments = [m for m in moments if m.crowd > 0 or m.energy >= 0.12]

    # two passes: first demand time spread (a batch of three clips from the
    # same 10 minutes is one clip posted thrice), then fill remaining slots
    # from whatever's left if spread alone can't reach count
    picked: list[Moment] = []
    ranked = sorted(
        moments,
        key=lambda x: (
            {"post": 2, "bench": 1, "reject": 0}.get(x.decision, 1),
            x.combined),
        reverse=True)
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
