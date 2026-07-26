// Presentation only: every number arrives already computed and priced by
// lib/costs.js, so nothing here can reach a secret or a provider API.
import { usd } from "../../../lib/llmPrices";
import CostsAutoRefresh from "./CostsAutoRefresh";

function clock(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h
    ? `${h}h ${String(m).padStart(2, "0")}m`
    : `${m}m ${String(s).padStart(2, "0")}s`;
}

function tokens(n) {
  const value = Number(n || 0);
  if (!value) return "0";
  if (value < 1000) return String(value);
  if (value < 1_000_000) return `${(value / 1000).toFixed(1)}k`;
  return `${(value / 1_000_000).toFixed(2)}M`;
}

const CARD = "rounded-2xl border border-[#23233a] bg-[#12121a]";
const HEAD = "text-sm font-bold text-gray-400 uppercase tracking-wide mb-3";

function Stat({ label, value, note }) {
  return (
    <div className={`${CARD} px-5 py-4`}>
      <div className="text-[11px] font-bold uppercase tracking-wide text-gray-500">
        {label}
      </div>
      <div className="mt-1 text-2xl font-black text-white">{value}</div>
      {note && <div className="mt-1 text-xs text-gray-500">{note}</div>}
    </div>
  );
}

function ModelLines({ models, empty = null }) {
  // Jobs that ran before the usage ledger existed have no models at all;
  // saying "no LLM calls" on every historical row would be a lie dressed as
  // data, so the table simply shows nothing there.
  if (!models.length) {
    return empty ? <span className="text-gray-600">{empty}</span> : null;
  }
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {models.map((m) => (
        <span key={m.model} className="text-gray-400">
          <span className="text-gray-300">{m.model}</span>{" "}
          {m.calls} calls
          {m.audioSeconds
            ? ` · ${(m.audioSeconds / 60).toFixed(1)} min audio`
            : ` · ${tokens(m.inputTokens)} in${
                m.cachedInputTokens
                  ? ` (+${tokens(m.cachedInputTokens)} cached)`
                  : ""
              } · ${tokens(m.outputTokens)} out${
                m.reasoningTokens
                  ? ` (${tokens(m.reasoningTokens)} reasoning)`
                  : ""
              }`}
        </span>
      ))}
    </div>
  );
}

// Always shown, even at zero: a provider silently missing from this table is
// indistinguishable from a provider that stopped being measured.
const ALWAYS_SHOWN = ["openai", "groq", "modal"];

export default function CostsView({ profile, data }) {
  const providerRows = [
    ...new Set([
      ...ALWAYS_SHOWN,
      ...Object.keys(data.monthProviders),
      ...Object.keys(data.todayProviders),
    ]),
  ];

  const openAiToday =
    data.orgCosts.state === "ok" ? data.orgCosts.today : null;
  const openAiMonth =
    data.orgCosts.state === "ok" ? data.orgCosts.month : null;

  return (
    <main className="max-w-6xl mx-auto px-6 py-10 text-sm">
      <CostsAutoRefresh />

      <div className="mb-8 flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-xl font-black text-white">
          Cost &amp; runs{" "}
          <span className="text-xs font-normal text-gray-500">
            founder only · {profile.twitch_login}
          </span>
        </h1>
        <div className="text-xs text-gray-500">
          days bucketed in UTC · refreshes every 3s ·{" "}
          {new Date(data.now).toISOString().replace("T", " ").slice(0, 19)}Z
        </div>
      </div>

      {data.health && (
        <div
          className={`${CARD} mb-6 px-5 py-3 text-xs ${
            data.health.delayed ? "text-amber-400" : "text-gray-500"
          }`}
        >
          worker {data.health.state}
          {data.health.heartbeatAgeSeconds != null
            ? ` · heartbeat ${data.health.heartbeatAgeSeconds}s ago`
            : " · no heartbeat"}
          {" · queue "}
          {data.health.queueDepth ?? "?"}
          {data.health.workerVersion ? ` · ${data.health.workerVersion}` : ""}
          {data.health.delayed &&
            " — a job shown as running may be orphaned; its Modal estimate keeps climbing until the 150 min requeue."}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-10">
        <Stat
          label="Spend today"
          value={usd(data.todayTotal)}
          note={
            openAiToday != null
              ? `OpenAI org says ${usd(openAiToday)}`
              : "measured from job ledgers"
          }
        />
        <Stat
          label="Spend month to date"
          value={usd(data.monthTotal)}
          note={
            openAiMonth != null
              ? `OpenAI org says ${usd(openAiMonth)}`
              : "measured from job ledgers"
          }
        />
        <Stat
          label="Avg cost / VOD"
          value={data.avgPerVod == null ? "—" : usd(data.avgPerVod)}
          note="last 10 completed jobs"
        />
        <Stat
          label="Credits outstanding"
          value={`${data.creditsOutstanding} GW`}
          note="sold, not yet burned — future compute liability"
        />
      </div>

      <h2 className={HEAD}>Running now</h2>
      <div className={`${CARD} mb-10 divide-y divide-[#1c1c2e]`}>
        {data.active.length === 0 ? (
          <div className="px-5 py-6 text-gray-500">
            Nothing running or queued.
          </div>
        ) : (
          data.active.map((job) => (
            <div key={job.id} className="px-5 py-4">
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={`text-[10px] font-black px-2 py-0.5 rounded-full border uppercase ${
                    job.status === "running"
                      ? "border-purple-800/70 bg-purple-950/30 text-purple-300"
                      : "border-[#2e2e4a] text-gray-400"
                  }`}
                >
                  {job.status}
                  {job.kind ? ` · ${job.kind}` : ""}
                </span>
                <a
                  href={job.vodUrl}
                  target="_blank"
                  className="text-purple-300 hover:underline"
                >
                  {String(job.vodUrl || "").replace("https://www.", "")}
                </a>
                <span className="text-gray-400">{job.login}</span>
                <span className="text-gray-500">
                  {job.stage || "—"}
                  {job.detail ? ` · ${job.detail}` : ""}
                </span>
                <span className="ml-auto flex items-center gap-4">
                  <span className="text-gray-400">
                    {clock(job.elapsedSeconds)}
                  </span>
                  <span className="font-black text-white">
                    {usd(job.totalUsd)}
                  </span>
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 text-xs">
                <span className="text-gray-500">
                  LLM {usd(job.llmUsd)} · Modal {usd(job.modalUsd)} est.
                </span>
                <ModelLines
                  models={job.models}
                  empty="no LLM calls recorded yet"
                />
              </div>
            </div>
          ))
        )}
      </div>

      <h2 className={HEAD}>Last 20 jobs</h2>
      <div className={`${CARD} mb-10 overflow-x-auto`}>
        <table className="w-full min-w-[820px] text-left">
          <thead className="text-[11px] uppercase tracking-wide text-gray-500">
            <tr className="border-b border-[#1c1c2e]">
              <th className="px-5 py-3 font-bold">VOD / user</th>
              <th className="px-3 py-3 font-bold">Status</th>
              <th className="px-3 py-3 font-bold">Duration</th>
              <th className="px-3 py-3 font-bold">Clips</th>
              <th className="px-3 py-3 font-bold text-right">LLM</th>
              <th className="px-3 py-3 font-bold text-right">Modal est.</th>
              <th className="px-5 py-3 font-bold text-right">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1c1c2e]">
            {data.recent.length === 0 ? (
              <tr>
                <td className="px-5 py-6 text-gray-500" colSpan={7}>
                  No completed jobs this month.
                </td>
              </tr>
            ) : (
              data.recent.map((job) => (
                <tr key={job.id} className="align-top">
                  <td className="px-5 py-3">
                    <a
                      href={job.vodUrl}
                      target="_blank"
                      className="text-purple-300 hover:underline"
                    >
                      {String(job.vodUrl || "").replace("https://www.", "")}
                    </a>
                    <div className="text-xs text-gray-500">
                      {job.login} ·{" "}
                      {new Date(
                        job.finishedAt || job.createdAt
                      ).toLocaleString()}
                    </div>
                    {job.status === "failed" && job.error && (
                      <div className="mt-1 text-xs text-red-400">
                        {job.error.slice(0, 160)}
                      </div>
                    )}
                    <div className="mt-1 text-xs">
                      <ModelLines models={job.models} />
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <span
                      className={
                        job.status === "done"
                          ? "text-green-400 font-semibold"
                          : "text-red-400 font-semibold"
                      }
                    >
                      {job.status}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-gray-400">
                    {clock(job.modalSeconds ?? job.elapsedSeconds)}
                  </td>
                  <td className="px-3 py-3 text-gray-400">
                    {job.clips}
                    {job.requested != null ? ` / ${job.requested}` : ""}
                    {job.chunksTotal != null &&
                      job.chunksScored != null &&
                      job.chunksScored < job.chunksTotal && (
                        <div className="mt-1 text-[10px] font-bold text-amber-400">
                          {job.chunksTotal - job.chunksScored} of{" "}
                          {job.chunksTotal} chunks unscored
                        </div>
                      )}
                  </td>
                  <td className="px-3 py-3 text-right text-gray-300">
                    {usd(job.llmUsd)}
                  </td>
                  <td className="px-3 py-3 text-right text-gray-300">
                    {usd(job.modalUsd)}
                  </td>
                  <td className="px-5 py-3 text-right font-black text-white">
                    {usd(job.totalUsd)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <h2 className={HEAD}>Provider totals</h2>
      <div className={`${CARD} mb-4 overflow-x-auto`}>
        <table className="w-full min-w-[520px] text-left">
          <thead className="text-[11px] uppercase tracking-wide text-gray-500">
            <tr className="border-b border-[#1c1c2e]">
              <th className="px-5 py-3 font-bold">Provider</th>
              <th className="px-3 py-3 font-bold text-right">Today</th>
              <th className="px-3 py-3 font-bold text-right">Month to date</th>
              <th className="px-5 py-3 font-bold">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1c1c2e]">
            {providerRows.map((provider) => {
              const orgKnown = provider === "openai" && openAiMonth != null;
              // Nothing in the ledger is not the same as zero spend: before
              // the first job runs the new ledger, "n/a" is the honest cell.
              const measured =
                provider in data.monthProviders ||
                provider in data.todayProviders;
              const cell = (orgValue, ledgerValue) =>
                orgKnown ? (
                  usd(orgValue)
                ) : measured ? (
                  usd(ledgerValue)
                ) : (
                  <span className="text-gray-600">n/a</span>
                );
              return (
                <tr key={provider}>
                  <td className="px-5 py-3 text-gray-300">{provider}</td>
                  <td className="px-3 py-3 text-right text-gray-300">
                    {cell(openAiToday, data.todayProviders[provider])}
                  </td>
                  <td className="px-3 py-3 text-right text-gray-300">
                    {cell(openAiMonth, data.monthProviders[provider])}
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-500">
                    {orgKnown
                      ? "OpenAI Costs API (org-wide)"
                      : provider === "modal"
                        ? "est. from wall time × published rate"
                        : measured
                          ? "per-call usage ledger"
                          : "per-call usage ledger — nothing recorded yet"}
                  </td>
                </tr>
              );
            })}
            {["Supabase", "Vercel", "Cloudflare R2"].map((name) => (
              <tr key={name}>
                <td className="px-5 py-3 text-gray-300">{name}</td>
                <td className="px-3 py-3 text-right text-gray-500">free tier</td>
                <td className="px-3 py-3 text-right text-gray-500">free tier</td>
                <td className="px-5 py-3 text-xs text-gray-500">
                  no usage API wired
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.orgCosts.state !== "ok" && (
        <div className={`${CARD} mb-4 px-5 py-4 text-xs text-gray-400`}>
          <span className="font-bold text-amber-400">
            OpenAI org totals unavailable
          </span>{" "}
          —{" "}
          {data.orgCosts.state === "missing_key"
            ? "add OPENAI_ADMIN_KEY to enable."
            : data.orgCosts.state === "unauthorized"
              ? "OPENAI_ADMIN_KEY is set but not authorized for the Costs API — it must be an Admin key, not a project key."
              : "the Costs API call failed; retrying on the next refresh."}{" "}
          Mint one at platform.openai.com → organization settings → Admin keys,
          then{" "}
          <code className="text-gray-300">
            npx vercel env add OPENAI_ADMIN_KEY production
          </code>
          . Until then the OpenAI row is the sum of this app&apos;s own per-call
          ledger, which misses spend from anything else on the org.
        </div>
      )}

      {data.unpricedModels.length > 0 && (
        <div className={`${CARD} px-5 py-4 text-xs text-gray-400`}>
          <span className="font-bold text-amber-400">Unpriced models</span> —
          used but missing from{" "}
          <code className="text-gray-300">lib/llmPrices.js</code>, so their
          spend is <em>not</em> in the totals above:{" "}
          {data.unpricedModels
            .map((m) => `${m.model} (${m.calls} calls)`)
            .join(", ")}
          .
        </div>
      )}
    </main>
  );
}
