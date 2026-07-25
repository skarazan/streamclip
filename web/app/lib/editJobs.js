import path from "node:path";
import { spawn } from "node:child_process";

export const serviceHeaders = (extra = {}) => ({
  apikey: process.env.SUPABASE_SERVICE_KEY,
  Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
  "Content-Type": "application/json",
  ...extra,
});

export const rest = (resource) =>
  `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1${resource}`;

export function wakeLocalWorker() {
  const enabled =
    process.env.NODE_ENV === "development" ||
    process.env.STREAMCLIP_LOCAL_WORKER === "1";
  if (!enabled || process.env.STREAMCLIP_LOCAL_WORKER === "0") return;
  const repo = path.resolve(process.cwd(), "../..");
  const python =
    process.env.STREAMCLIP_PYTHON ||
    path.resolve(repo, "../clipfarm/.venv/bin/python");
  const child = spawn(python, ["-u", "worker/worker.py", "--once"], {
    cwd: repo,
    detached: true,
    stdio: "ignore",
    env: { ...process.env, WORKER_ID: "local-dashboard-edit" },
  });
  child.unref();
}

export async function ownedClip(id, userId) {
  const rows = await fetch(
    rest(`/clips?id=eq.${id}&user_id=eq.${userId}&select=*`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((r) => r.json());
  return rows?.[0] || null;
}
