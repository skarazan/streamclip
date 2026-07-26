// Server-only cost aggregation for /admin/costs.
//
// Everything here runs with the Supabase service key and, optionally, the
// OpenAI admin key. Nothing in this file may be imported from a client
// component: the page passes plain numbers down, never these functions.

import { rest, serviceHeaders } from "./editJobs";
import { readServiceHealth } from "./serviceHealth";
import { jobCost } from "./llmPrices";

// Legacy admin marker. `plan` is billing's column — Stripe rewrites it on
// checkout and cancellation — so admin rights live in `users.is_admin`. These
// values remain the fallback until 20260725_admin_flag.sql is applied.
export const FOUNDER_PLANS = ["founder", "internal"];

const isAdmin = (row) =>
  row?.is_admin === true ||
  (row?.is_admin === undefined && FOUNDER_PLANS.includes(row?.plan));

/**
 * Admin gate. Returns the profile row when the signed-in user is allowed to
 * see house financials, otherwise null — callers turn that into a 404, not a
 * 403, so the route's existence isn't advertised.
 *
 * Read with the service key: `users` RLS lets a user select their own row,
 * but the gate should not depend on a policy staying that way.
 */
export async function founderProfile(sb) {
  const {
    data: { user },
  } = await sb.auth.getUser();
  if (!user) return null;
  const select = async (columns) =>
    fetch(rest(`/users?id=eq.${user.id}&select=${columns}`), {
      headers: serviceHeaders(),
      cache: "no-store",
    })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
  // Additive rollout: the old schema stays usable until the founder applies
  // the migration, and `is_admin` being absent is what selects the fallback.
  const rows =
    (await select("id,twitch_login,plan,is_admin")) ||
    (await select("id,twitch_login,plan")) ||
    [];
  const profile = rows?.[0];
  if (!profile || !isAdmin(profile)) return null;
  return profile;
}

// Day/month boundaries are UTC so the figures line up with the OpenAI
// dashboard, which buckets org spend in UTC.
function utcBoundaries(now) {
  const d = new Date(now);
  const dayStart = Date.UTC(
    d.getUTCFullYear(),
    d.getUTCMonth(),
    d.getUTCDate()
  );
  const monthStart = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
  return { dayStart, monthStart };
}

function addProviders(target, byProvider) {
  for (const [provider, usd] of Object.entries(byProvider)) {
    target[provider] = (target[provider] || 0) + usd;
  }
}

/**
 * Org-wide OpenAI spend. Needs an Admin API key, which a normal
 * OPENAI_API_KEY is not — so the absent/unauthorized case is a first-class
 * result, never an exception that takes the page down with it.
 */
export async function openAiOrgCosts(monthStartMs, now = Date.now()) {
  const key = process.env.OPENAI_ADMIN_KEY;
  if (!key) {
    return { state: "missing_key", today: null, month: null, days: [] };
  }
  try {
    const url =
      "https://api.openai.com/v1/organization/costs" +
      `?start_time=${Math.floor(monthStartMs / 1000)}` +
      "&bucket_width=1d&limit=31";
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${key}` },
      cache: "no-store",
    });
    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized", today: null, month: null, days: [] };
    }
    if (!response.ok) {
      return { state: "error", today: null, month: null, days: [] };
    }
    const payload = await response.json();
    const { dayStart } = utcBoundaries(now);
    let month = 0;
    let today = 0;
    const days = [];
    for (const bucket of payload?.data || []) {
      const amount = (bucket?.results || []).reduce(
        (sum, row) => sum + Number(row?.amount?.value || 0),
        0
      );
      month += amount;
      const bucketStartMs = Number(bucket?.start_time || 0) * 1000;
      if (bucketStartMs >= dayStart) today += amount;
      days.push({ startMs: bucketStartMs, usd: amount });
    }
    return { state: "ok", today, month, days };
  } catch {
    return { state: "error", today: null, month: null, days: [] };
  }
}

/**
 * Everything the founder page renders, as plain numbers.
 * One jobs query covers all four panels: this month's finished work plus
 * anything currently in flight.
 */
export async function collectCosts(now = Date.now()) {
  const { dayStart, monthStart } = utcBoundaries(now);
  const monthStartIso = new Date(monthStart).toISOString();

  const jobsQuery =
    "/jobs?select=id,user_id,vod_url,status,created_at,started_at,finished_at,error,progress" +
    `&or=(finished_at.gte.${encodeURIComponent(monthStartIso)},status.in.(queued,running))` +
    "&order=created_at.desc&limit=2000";

  const [jobs, users, clips, orgCosts, health] = await Promise.all([
    fetch(rest(jobsQuery), { headers: serviceHeaders(), cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .catch(() => []),
    fetch(rest("/users?select=id,twitch_login,plan,credits,is_admin"), {
      headers: serviceHeaders(),
      cache: "no-store",
    })
      .then((r) =>
        r.ok
          ? r.json()
          : // Pre-migration schema: retry without the new column.
            fetch(rest("/users?select=id,twitch_login,plan,credits"), {
              headers: serviceHeaders(),
              cache: "no-store",
            }).then((f) => (f.ok ? f.json() : []))
      )
      .catch(() => []),
    fetch(rest("/clips?select=job_id&limit=5000"), {
      headers: serviceHeaders(),
      cache: "no-store",
    })
      .then((r) => (r.ok ? r.json() : []))
      .catch(() => []),
    openAiOrgCosts(monthStart, now),
    // A "running" job whose worker stopped heartbeating is still accruing a
    // Modal estimate on this page; the founder needs to see which it is.
    readServiceHealth().catch(() => null),
  ]);

  const loginById = new Map((users || []).map((u) => [u.id, u.twitch_login]));
  const clipCount = new Map();
  for (const clip of clips || []) {
    clipCount.set(clip.job_id, (clipCount.get(clip.job_id) || 0) + 1);
  }

  const monthProviders = {};
  const todayProviders = {};
  let monthTotal = 0;
  let todayTotal = 0;
  const unpricedModels = new Map();

  const decorate = (job) => {
    const cost = jobCost(job, now);
    const usage = job?.progress?.llm_usage || {};
    return {
      id: job.id,
      vodUrl: job.vod_url,
      login: loginById.get(job.user_id) || job.user_id?.slice(0, 8) || "—",
      status: job.status,
      kind: job.progress?.kind || null,
      stage: job.progress?.stage || null,
      detail: job.progress?.detail || "",
      error: job.error ? String(job.error).split("\n").slice(-1)[0] : null,
      createdAt: job.created_at,
      startedAt: job.started_at,
      finishedAt: job.finished_at,
      elapsedSeconds: job.started_at
        ? Math.max(
            0,
            ((job.finished_at ? new Date(job.finished_at).getTime() : now) -
              new Date(job.started_at).getTime()) /
              1000
          )
        : null,
      clips: clipCount.get(job.id) || 0,
      requested: job.progress?.requested ?? null,
      // Chunks lost on every model. That stream time produced no candidates,
      // so a thin batch has a cause instead of looking like a weak VOD.
      chunksTotal: job.progress?.chunks_total ?? null,
      chunksScored: job.progress?.chunks_scored ?? null,
      models: Object.entries(usage).map(([model, entry]) => ({
        model,
        calls: Number(entry.calls || 0),
        inputTokens: Number(entry.input_tokens || 0),
        cachedInputTokens: Number(entry.cached_input_tokens || 0),
        outputTokens: Number(entry.output_tokens || 0),
        reasoningTokens: Number(entry.reasoning_tokens || 0),
        audioSeconds: Number(entry.audio_seconds || 0),
      })),
      llmUsd: cost.llm.total,
      llmByProvider: cost.llm.byProvider,
      modalUsd: cost.modal.usd,
      modalSeconds: cost.modal.seconds,
      totalUsd: cost.total,
      unpriced: cost.llm.unpriced,
    };
  };

  const decorated = (jobs || []).map(decorate);

  for (const job of decorated) {
    for (const entry of job.unpriced) {
      unpricedModels.set(
        entry.model,
        (unpricedModels.get(entry.model) || 0) + entry.calls
      );
    }
    const providers = { ...job.llmByProvider, modal: job.modalUsd };
    // A running job's spend belongs to today; a finished one to the day it
    // finished. Partial usage is exactly what "cost so far" means.
    const stampMs = job.finishedAt
      ? new Date(job.finishedAt).getTime()
      : now;
    addProviders(monthProviders, providers);
    monthTotal += job.totalUsd;
    if (stampMs >= dayStart) {
      addProviders(todayProviders, providers);
      todayTotal += job.totalUsd;
    }
  }

  const active = decorated.filter(
    (job) => job.status === "running" || job.status === "queued"
  );
  const recent = decorated
    .filter(
      (job) => !job.kind && (job.status === "done" || job.status === "failed")
    )
    .sort(
      (a, b) =>
        new Date(b.finishedAt || b.createdAt) -
        new Date(a.finishedAt || a.createdAt)
    )
    .slice(0, 20);

  const lastTen = recent.filter((job) => job.status === "done").slice(0, 10);
  const avgPerVod = lastTen.length
    ? lastTen.reduce((sum, job) => sum + job.totalUsd, 0) / lastTen.length
    : null;

  // Credits already sold but not yet burned — future compute we owe.
  // Admin balances are house money, not a liability.
  const creditsOutstanding = (users || [])
    .filter((u) => !isAdmin(u))
    .reduce((sum, u) => sum + Number(u.credits || 0), 0);

  return {
    now,
    dayStart,
    monthStart,
    active,
    recent,
    monthTotal,
    todayTotal,
    monthProviders,
    todayProviders,
    avgPerVod,
    creditsOutstanding,
    unpricedModels: [...unpricedModels.entries()].map(([model, calls]) => ({
      model,
      calls,
    })),
    orgCosts,
    health,
  };
}
