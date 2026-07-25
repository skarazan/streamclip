// Prices live in the web app on purpose. The worker records only what it
// consumed (clipfarm/usage.py); pricing here means a provider price change is
// a Vercel deploy instead of a Modal worker redeploy mid-queue.
//
// Rates are USD. Token rates are per 1M tokens, audio rates per hour.
// Founder: check these against the provider pricing pages when a number on
// /admin/costs looks wrong — a stale rate here is the most likely cause.
// Last reviewed 2026-07-25.

export const TOKEN_PRICES = {
  // OpenAI. Reasoning tokens are billed as output and are already inside the
  // completion count, so they are never charged twice.
  "gpt-5-mini": { in: 0.25, cachedIn: 0.025, out: 2.0, provider: "openai" },
  "gpt-5": { in: 1.25, cachedIn: 0.125, out: 10.0, provider: "openai" },
  "gpt-5-nano": { in: 0.05, cachedIn: 0.005, out: 0.4, provider: "openai" },

  // Groq — the fallback rung of the scoring chain.
  "llama-3.3-70b-versatile": { in: 0.59, out: 0.79, provider: "groq" },

  // Free tiers: real usage, zero invoice. Priced explicitly so they show as
  // $0.00 rather than falling into the "unpriced" bucket.
  "gemini-3.5-flash": { in: 0, out: 0, provider: "google" },
  "gemini-3.6-flash": { in: 0, out: 0, provider: "google" },
  // Runs on the founder's Claude subscription; the CLI reports no usage.
  "claude-code": { in: 0, out: 0, provider: "anthropic", metered: false },
};

// Whisper is billed per second of audio, not per token.
export const AUDIO_PRICES = {
  "whisper-large-v3-turbo": { perHour: 0.04, provider: "groq" },
  "whisper-large-v3": { perHour: 0.111, provider: "groq" },
};

// Must match worker/worker.py's estimate, or a running job's figure would
// jump when the job finishes and the worker's own number takes over.
export const MODAL_CORES = 8;
export const MODAL_CPU_USD_PER_CORE_S = 0.0000131;
export const MODAL_GIB_USD_PER_GIB_S = 0.00000222;
export const MODAL_USD_PER_SECOND =
  MODAL_CORES * MODAL_CPU_USD_PER_CORE_S + MODAL_CORES * MODAL_GIB_USD_PER_GIB_S;

export function providerOf(model) {
  return (
    TOKEN_PRICES[model]?.provider ||
    AUDIO_PRICES[model]?.provider ||
    (model?.startsWith("gpt-") || model?.startsWith("o1") ? "openai" : null) ||
    (model?.startsWith("gemini") ? "google" : null) ||
    (model?.startsWith("claude") ? "anthropic" : null) ||
    (model?.startsWith("whisper") || model?.startsWith("llama") ? "groq" : null) ||
    "unknown"
  );
}

/**
 * Cost of one model's line in a `progress.llm_usage` ledger.
 * `priced` is false when the model has no rate here — the caller shows
 * "unpriced" instead of implying the calls were free.
 */
export function costForModel(model, entry) {
  const tokens = TOKEN_PRICES[model];
  const audio = AUDIO_PRICES[model];
  if (!tokens && !audio) {
    return { usd: 0, priced: false, provider: providerOf(model) };
  }
  let usd = 0;
  if (tokens) {
    const cached = Number(entry?.cached_input_tokens || 0);
    // A model without a published cache rate bills cached input at full price.
    const cachedRate = tokens.cachedIn ?? tokens.in;
    usd +=
      (Number(entry?.input_tokens || 0) * tokens.in +
        cached * cachedRate +
        Number(entry?.output_tokens || 0) * tokens.out) /
      1_000_000;
  }
  if (audio) {
    usd += (Number(entry?.audio_seconds || 0) / 3600) * audio.perHour;
  }
  return { usd, priced: true, provider: providerOf(model) };
}

/**
 * Price a whole `progress.llm_usage` object.
 * Returns the total plus a per-provider breakdown and the models we had no
 * rate for, so the page can say so out loud.
 */
export function costForUsage(usage) {
  const byProvider = {};
  const unpriced = [];
  let total = 0;
  for (const [model, entry] of Object.entries(usage || {})) {
    const { usd, priced, provider } = costForModel(model, entry);
    if (!priced) {
      unpriced.push({ model, calls: Number(entry?.calls || 0) });
      continue;
    }
    total += usd;
    byProvider[provider] = (byProvider[provider] || 0) + usd;
  }
  return { total, byProvider, unpriced };
}

/**
 * Modal compute for a job. Completed jobs carry the worker's own figure;
 * a running job is estimated from wall time so far, using the same rate.
 */
export function modalCostForJob(job, now = Date.now()) {
  const recorded = Number(job?.progress?.estimated_modal_compute_usd);
  if (Number.isFinite(recorded) && recorded > 0) {
    return { usd: recorded, seconds: Number(job?.progress?.processing_seconds) || null };
  }
  const startedAt = job?.started_at ? new Date(job.started_at).getTime() : null;
  if (!startedAt) return { usd: 0, seconds: null };
  const endAt = job?.finished_at ? new Date(job.finished_at).getTime() : now;
  const seconds = Math.max(0, (endAt - startedAt) / 1000);
  return { usd: seconds * MODAL_USD_PER_SECOND, seconds };
}

/** Full picture for one job row: LLM + Modal. */
export function jobCost(job, now = Date.now()) {
  const llm = costForUsage(job?.progress?.llm_usage);
  const modal = modalCostForJob(job, now);
  return { llm, modal, total: llm.total + modal.usd };
}

export function usd(value) {
  const n = Number(value || 0);
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}
