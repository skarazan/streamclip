import { readServiceHealth } from "../../lib/serviceHealth";
import SiteFooter from "../components/SiteFooter";
import SiteHeader from "../components/SiteHeader";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Status — StreamClip",
  description: "Current StreamClip dashboard and processing status.",
};

export default async function StatusPage() {
  const health = await readServiceHealth();
  return (
    <>
    <SiteHeader />
    <main className="mx-auto max-w-3xl px-6 py-20">
      <p className="text-xs font-black uppercase tracking-[0.2em] text-purple-300">
        Service status
      </p>
      <h1 className="mt-3 text-4xl font-black">StreamClip systems</h1>
      <div className={`mt-8 rounded-3xl border p-7 ${
        health.ok
          ? "border-green-800/60 bg-green-950/20"
          : "border-amber-700/60 bg-amber-950/20"
      }`}>
        <p className="text-2xl font-black">
          {health.configured === false
            ? "Health telemetry pending deployment"
            : health.ok ? "All systems operational" : "Processing delayed"}
        </p>
        <p className="mt-2 text-sm text-gray-400">
          The web dashboard remains available independently from processing.
          Existing clips can still be viewed and downloaded.
        </p>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-gray-500">Worker</dt>
            <dd className="mt-1 font-bold">{health.state}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-gray-500">Queue</dt>
            <dd className="mt-1 font-bold">
              {health.queueDepth == null ? "Unknown" : `${health.queueDepth} waiting`}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-gray-500">Last heartbeat</dt>
            <dd className="mt-1 font-bold">
              {health.heartbeatAt
                ? new Date(health.heartbeatAt).toLocaleString()
                : "Not reported"}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-gray-500">Failures (24h)</dt>
            <dd className="mt-1 font-bold">{health.recentFailureCount}</dd>
          </div>
        </dl>
      </div>
    </main>
    <SiteFooter />
    </>
  );
}
