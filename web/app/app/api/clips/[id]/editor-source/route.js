import { NextResponse } from "next/server";
import { serverClient } from "../../../../../lib/supabase";
import {
  ownedClip, rest, serviceHeaders, wakeLocalWorker,
} from "../../../../../lib/editJobs";

export async function POST(_request, { params }) {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const clip = await ownedClip(params.id, user.id);
  if (!clip) return NextResponse.json({ error: "clip not found" }, { status: 404 });
  const prior = await fetch(
    rest(`/jobs?user_id=eq.${user.id}&status=in.(queued,processing,done)&select=id,status,progress&order=created_at.desc&limit=50`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((r) => r.json());
  const reusable = prior.find((j) =>
    j.progress?.kind === "clip_source" &&
    j.progress?.clip_id === clip.id &&
    j.progress?.proxy_version === 3 &&
    (j.status !== "done" || (
      j.progress?.proxy_key &&
      j.progress?.proxy_width === 360 &&
      j.progress?.proxy_height === 640 &&
      Array.isArray(j.progress?.waveform)
    ))
  );
  if (reusable) {
    return NextResponse.json({ ok: true, job_id: reusable.id, reused: true });
  }

  const original = await fetch(
    rest(`/jobs?id=eq.${clip.job_id}&select=vod_url,progress`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((r) => r.json());
  const parent = original?.[0];
  if (!parent) return NextResponse.json({ error: "source job not found" }, { status: 404 });
  const recipe = parent.progress?.clip_recipes?.[clip.id] || {
    source_start: Number(clip.start_s),
    source_end: Number(clip.end_s),
    keep_intervals: [[Number(clip.start_s), Number(clip.end_s)]],
    cam: null,
  };
  const sourceStart = Math.max(
    0, Math.min(Number(recipe.source_start), Number(clip.start_s)) - 30);
  const sourceEnd = Math.max(
    Number(recipe.source_end), Number(clip.end_s)) + 30;
  const ins = await fetch(rest("/jobs"), {
    method: "POST",
    headers: serviceHeaders({ Prefer: "return=representation" }),
    body: JSON.stringify({
      user_id: user.id,
      vod_url: parent.vod_url,
      status: "queued",
      progress: {
        kind: "clip_source", stage: "queued", clip_id: clip.id,
        proxy_version: 3,
        source_start: sourceStart, source_end: sourceEnd, recipe,
      },
    }),
  });
  if (!ins.ok) return NextResponse.json({ error: "couldn’t prepare editor" }, { status: 500 });
  const [job] = await ins.json();
  wakeLocalWorker();
  return NextResponse.json({ ok: true, job_id: job.id });
}
