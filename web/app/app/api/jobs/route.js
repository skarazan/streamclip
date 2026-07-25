import { NextResponse } from "next/server";
import { serverClient } from "../../../lib/supabase";
import path from "node:path";
import { spawn } from "node:child_process";

// accepts twitch.tv/videos/123, www., m., with or without query junk
const VOD_RE = /^https?:\/\/(?:www\.|m\.)?twitch\.tv\/videos\/(\d+)/;

const svcHeaders = () => ({
  apikey: process.env.SUPABASE_SERVICE_KEY,
  Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
  "Content-Type": "application/json",
});
const rest = (path) =>
  `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1${path}`;

function wakeLocalWorker() {
  const enabled =
    process.env.NODE_ENV === "development" ||
    process.env.STREAMCLIP_LOCAL_WORKER === "1";
  if (!enabled || process.env.STREAMCLIP_LOCAL_WORKER === "0") return;

  // web/app -> repository root; the project brief defines the shared Python
  // environment as the sibling clipfarm/.venv.
  const repo = path.resolve(process.cwd(), "../..");
  const python =
    process.env.STREAMCLIP_PYTHON ||
    path.resolve(repo, "../clipfarm/.venv/bin/python");
  const child = spawn(python, ["-u", "worker/worker.py", "--once"], {
    cwd: repo,
    detached: true,
    stdio: "ignore",
    env: { ...process.env, WORKER_ID: "local-dashboard" },
  });
  child.on("error", (error) => {
    console.error("local worker failed to start", error);
  });
  child.unref();
}

export async function POST(request) {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await request.json().catch(() => ({}));
  const m = String(body.vod_url || "").trim().match(VOD_RE);
  if (!m) {
    return NextResponse.json(
      { error: "that doesn't look like a Twitch VOD link (twitch.tv/videos/…)" },
      { status: 400 });
  }
  const vod_url = `https://www.twitch.tv/videos/${m[1]}`;

  // service key past this point: credits/queue state are the house's books.
  // The worker re-checks everything (credits, own-channel, VOD length) —
  // this route exists to fail fast and keep the queue clean.
  const users = await fetch(
    rest(`/users?id=eq.${user.id}&select=credits,clips_per_stream,style_profile`),
    { headers: svcHeaders(), cache: "no-store" }).then((r) => r.json());
  if (!users?.[0]) {
    return NextResponse.json({ error: "account not found" }, { status: 500 });
  }
  if ((users[0].credits ?? 0) < 1) {
    return NextResponse.json(
      { error: "not enough gigawatts — top up to keep clipping" },
      { status: 402 });
  }
  const requestedCount = Number.isInteger(Number(body.clips_per_stream)) &&
    Number(body.clips_per_stream) >= 1 && Number(body.clips_per_stream) <= 8
      ? Number(body.clips_per_stream)
      : (users[0].clips_per_stream || 3);

  const active = await fetch(
    rest(`/jobs?user_id=eq.${user.id}&status=in.(queued,running)&select=id,status,created_at,progress`),
    { headers: svcHeaders(), cache: "no-store" }).then((r) => r.json());
  const activeVodJobs = (active || []).filter((j) => !j.progress?.kind);
  if (activeVodJobs.length) {
    const age = Math.round(
      (Date.now() - new Date(activeVodJobs[0].created_at).getTime()) / 60000);
    return NextResponse.json(
      { error: activeVodJobs[0].status === "queued" && age > 15
          ? `a job from ${age} min ago is still waiting in the queue — it runs first, then you can submit this one`
          : "a clip job is already running — one stream at a time" },
      { status: 409 });
  }

  const ins = await fetch(rest("/jobs"), {
    method: "POST",
    headers: { ...svcHeaders(), Prefer: "return=representation" },
    // Snapshot settings at submit time. A later dashboard change applies to
    // the next run, never mutates the meaning of an already queued job.
    body: JSON.stringify({
      user_id: user.id,
      vod_url,
      status: "queued",
      progress: {
        stage: "queued",
        settings_snapshot: {
          clips_per_stream: requestedCount,
          style_profile: users[0].style_profile || {},
        },
      },
    }),
  });
  if (!ins.ok) {
    return NextResponse.json({ error: "couldn't queue the job" }, { status: 500 });
  }
  const [job] = await ins.json();
  wakeLocalWorker();
  return NextResponse.json({ ok: true, id: job.id });
}
