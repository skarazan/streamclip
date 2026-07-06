import { NextResponse } from "next/server";
import { serverClient } from "../../../lib/supabase";

// accepts twitch.tv/videos/123, www., m., with or without query junk
const VOD_RE = /^https?:\/\/(?:www\.|m\.)?twitch\.tv\/videos\/(\d+)/;

const svcHeaders = () => ({
  apikey: process.env.SUPABASE_SERVICE_KEY,
  Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
  "Content-Type": "application/json",
});
const rest = (path) =>
  `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1${path}`;

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
    rest(`/users?id=eq.${user.id}&select=credits`),
    { headers: svcHeaders(), cache: "no-store" }).then((r) => r.json());
  if (!users?.[0]) {
    return NextResponse.json({ error: "account not found" }, { status: 500 });
  }
  if ((users[0].credits ?? 0) < 1) {
    return NextResponse.json(
      { error: "not enough gigawatts — top up to keep clipping" },
      { status: 402 });
  }

  const active = await fetch(
    rest(`/jobs?user_id=eq.${user.id}&status=in.(queued,running)&select=id,status,created_at`),
    { headers: svcHeaders(), cache: "no-store" }).then((r) => r.json());
  if (active?.length) {
    const age = Math.round(
      (Date.now() - new Date(active[0].created_at).getTime()) / 60000);
    return NextResponse.json(
      { error: active[0].status === "queued" && age > 15
          ? `a job from ${age} min ago is still waiting in the queue — it runs first, then you can submit this one`
          : "a clip job is already running — one stream at a time" },
      { status: 409 });
  }

  const ins = await fetch(rest("/jobs"), {
    method: "POST",
    headers: { ...svcHeaders(), Prefer: "return=representation" },
    body: JSON.stringify({ user_id: user.id, vod_url, status: "queued" }),
  });
  if (!ins.ok) {
    return NextResponse.json({ error: "couldn't queue the job" }, { status: 500 });
  }
  const [job] = await ins.json();
  return NextResponse.json({ ok: true, id: job.id });
}
