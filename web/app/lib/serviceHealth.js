import { rest, serviceHeaders } from "./editJobs";

export async function readServiceHealth() {
  const now = Date.now();
  try {
    const [workersResponse, jobsResponse] = await Promise.all([
      fetch(
        rest("/worker_health?select=id,state,queue_depth,worker_version,detail,updated_at&order=updated_at.desc&limit=10"),
        { headers: serviceHeaders(), cache: "no-store" }
      ),
      fetch(
        rest("/jobs?select=status,created_at,started_at,finished_at&order=created_at.desc&limit=100"),
        { headers: serviceHeaders(), cache: "no-store" }
      ),
    ]);
    if (!jobsResponse.ok) throw new Error("job health unavailable");
    const workers = workersResponse.ok ? await workersResponse.json() : [];
    const jobs = await jobsResponse.json();
    if (!workersResponse.ok) {
      return {
        ok: null,
        delayed: false,
        configured: false,
        state: "telemetry_pending",
        heartbeatAt: null,
        heartbeatAgeSeconds: null,
        queueDepth: jobs.filter((job) => job.status === "queued").length,
        workerVersion: null,
        recentCompleted: jobs.filter((job) => job.status === "done").slice(0, 10),
        recentFailureCount: jobs.filter(
          (job) => job.status === "failed" &&
            now - new Date(job.created_at).getTime() < 24 * 60 * 60_000
        ).length,
      };
    }
    const newest = workers?.[0] || null;
    const ageMs = newest?.updated_at
      ? now - new Date(newest.updated_at).getTime()
      : Infinity;
    const delayed = ageMs > 5 * 60_000;
    const completed = jobs.filter((job) => job.status === "done");
    const failed = jobs.filter((job) => job.status === "failed");
    const active = jobs.filter(
      (job) => job.status === "queued" || job.status === "running"
    );
    return {
      ok: !delayed,
      delayed,
      configured: true,
      state: delayed ? "delayed" : newest?.state || "idle",
      heartbeatAt: newest?.updated_at || null,
      heartbeatAgeSeconds: Number.isFinite(ageMs)
        ? Math.max(0, Math.round(ageMs / 1000))
        : null,
      queueDepth: Math.max(
        Number(newest?.queue_depth || 0),
        active.filter((job) => job.status === "queued").length
      ),
      workerVersion: newest?.worker_version || null,
      recentCompleted: completed.slice(0, 10),
      recentFailureCount: failed.filter(
        (job) => now - new Date(job.created_at).getTime() < 24 * 60 * 60_000
      ).length,
    };
  } catch {
    return {
      ok: false,
      delayed: true,
      configured: true,
      state: "unknown",
      heartbeatAt: null,
      heartbeatAgeSeconds: null,
      queueDepth: null,
      workerVersion: null,
      recentCompleted: [],
      recentFailureCount: 0,
    };
  }
}
