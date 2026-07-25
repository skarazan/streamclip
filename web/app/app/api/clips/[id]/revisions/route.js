import { NextResponse } from "next/server";
import { serverClient } from "../../../../../lib/supabase";
import {
  ownedClip, rest, serviceHeaders, wakeLocalWorker,
} from "../../../../../lib/editJobs";

export async function POST(request, { params }) {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const clip = await ownedClip(params.id, user.id);
  if (!clip) return NextResponse.json({ error: "clip not found" }, { status: 404 });
  const body = await request.json().catch(() => ({}));
  const sourceJob = await fetch(
    rest(`/jobs?id=eq.${body.source_job_id}&user_id=eq.${user.id}&select=vod_url,status,progress`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((r) => r.json());
  const source = sourceJob?.[0];
  if (!source || source.status !== "done" || source.progress?.kind !== "clip_source") {
    return NextResponse.json({ error: "editor source is not ready" }, { status: 409 });
  }
  const start = Number(body.source_start);
  const end = Number(body.source_end);
  const lo = Number(source.progress.source_start);
  const hi = Number(source.progress.source_end);
  const keep = Array.isArray(body.keep_intervals)
    ? body.keep_intervals.map(([a, b]) => [Number(a), Number(b)])
    : [];
  const valid = Number.isFinite(start) && Number.isFinite(end) &&
    start >= lo && end <= hi && end > start &&
    keep.length > 0 && keep.every(([a, b], i) =>
      Number.isFinite(a) && Number.isFinite(b) && a >= start && b <= end &&
      b > a && (i === 0 || a >= keep[i - 1][1]));
  const retained = keep.reduce((n, [a, b]) => n + b - a, 0);
  if (!valid || retained < 3 || retained > 90) {
    return NextResponse.json(
      { error: "invalid edit (keep between 3 and 90 seconds)" },
      { status: 400 }
    );
  }
  const profile = await fetch(
    rest(`/users?id=eq.${user.id}&select=style_profile`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((r) => r.json());
  const p = {
    kind: "clip_edit", stage: "queued", clip_id: clip.id,
    source_job_id: body.source_job_id, source_start: start, source_end: end,
    keep_intervals: keep,
    cam: source.progress.cam || source.progress.recipe?.cam || null,
    hook: clip.hook || "", style_profile: profile?.[0]?.style_profile || {},
  };
  const ins = await fetch(rest("/jobs"), {
    method: "POST",
    headers: serviceHeaders({ Prefer: "return=representation" }),
    body: JSON.stringify({
      user_id: user.id, vod_url: source.vod_url, status: "queued", progress: p,
    }),
  });
  if (!ins.ok) return NextResponse.json({ error: "couldn’t queue revision" }, { status: 500 });
  const [job] = await ins.json();
  wakeLocalWorker();
  return NextResponse.json({ ok: true, job_id: job.id });
}
