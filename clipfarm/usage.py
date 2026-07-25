"""Per-process ledger of paid API usage (LLM tokens, Groq audio seconds).

Prices are deliberately NOT here. The worker records what was consumed; the
founder dashboard multiplies by a price table it owns, so a provider price
change is a web deploy instead of a worker redeploy.

Scoring runs on a thread pool, so every mutation takes the lock. Nothing in
this module may raise into a pipeline run — a broken telemetry read must not
cost a job that already paid for its tokens.
"""

from __future__ import annotations

import threading

_LOCK = threading.Lock()
_LEDGER: dict[str, dict[str, float]] = {}

_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens",
           "reasoning_tokens", "audio_seconds", "calls")


def reset() -> None:
    """Start a fresh ledger. The worker calls this per claimed job so a
    long-lived container doesn't bill job N for job N-1's tokens."""
    with _LOCK:
        _LEDGER.clear()


def record(model: str, *, input_tokens: float = 0, cached_input_tokens: float = 0,
           output_tokens: float = 0, reasoning_tokens: float = 0,
           audio_seconds: float = 0, calls: float = 1) -> None:
    if not model:
        return
    with _LOCK:
        entry = _LEDGER.setdefault(model, {f: 0 for f in _FIELDS})
        entry["input_tokens"] += input_tokens or 0
        entry["cached_input_tokens"] += cached_input_tokens or 0
        entry["output_tokens"] += output_tokens or 0
        entry["reasoning_tokens"] += reasoning_tokens or 0
        entry["audio_seconds"] += audio_seconds or 0
        entry["calls"] += calls or 0


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def record_response(model: str, resp) -> None:
    """Accumulate a provider response's usage block.

    Handles both shapes we call: OpenAI-compatible chat completions
    (prompt/completion_tokens) and the Anthropic Messages API
    (input/output_tokens). Reasoning tokens are billed as output and are
    already inside `completion_tokens`, so they are tracked separately only
    for display — never added on top, or gpt-5-mini double-bills.
    """
    try:
        usage = getattr(resp, "usage", None)
        if usage is None:
            return
        get = (usage.get if isinstance(usage, dict)
               else lambda k, d=None: getattr(usage, k, d))

        output = _num(get("completion_tokens")) or _num(get("output_tokens"))
        reasoning = 0.0
        details = get("completion_tokens_details")
        if details is not None:
            d_get = (details.get if isinstance(details, dict)
                     else lambda k, d=None: getattr(details, k, d))
            reasoning = _num(d_get("reasoning_tokens"))

        # Cached input is billed at a discount; keeping it in its own bucket
        # is the difference between a believable estimate and a wrong one.
        cached = _num(get("cache_read_input_tokens"))
        prompt_details = get("prompt_tokens_details")
        if prompt_details is not None:
            p_get = (prompt_details.get if isinstance(prompt_details, dict)
                     else lambda k, d=None: getattr(prompt_details, k, d))
            cached = cached or _num(p_get("cached_tokens"))

        # OpenAI's prompt_tokens already includes the cached portion;
        # Anthropic's input_tokens excludes both cache buckets.
        total_input = _num(get("prompt_tokens")) or (
            _num(get("input_tokens"))
            + _num(get("cache_creation_input_tokens")) + cached)
        record(model,
               input_tokens=max(0.0, total_input - cached),
               cached_input_tokens=cached,
               output_tokens=output,
               reasoning_tokens=reasoning)
    except Exception:
        # Usage telemetry is never worth failing a paid run over.
        pass


def record_call(model: str) -> None:
    """A billed call whose usage the provider didn't report (e.g. the Claude
    Code CLI, which runs on a subscription). Counted so the dashboard can say
    'N calls, tokens unknown' instead of silently showing $0."""
    record(model, calls=1)


def snapshot() -> dict[str, dict[str, float]]:
    """JSON-safe copy for `jobs.progress.llm_usage`. Zero fields are dropped so
    the jsonb stays small on jobs that only used one provider."""
    with _LOCK:
        return {
            model: {k: (round(v, 2) if k == "audio_seconds" else int(v))
                    for k, v in entry.items() if v}
            for model, entry in _LEDGER.items()
        }
