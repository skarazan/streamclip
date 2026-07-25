import { NextResponse } from "next/server";
import { serverClient } from "../../../lib/supabase";

export async function GET() {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const [{ data: jobs }, { data: clips }] = await Promise.all([
    sb.from("jobs")
      .select("id,status,progress,created_at,finished_at")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
      .limit(20),
    sb.from("clips")
      .select("id,job_id,r2_key,created_at")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
      .limit(30),
  ]);

  // Stable digest inputs only. Signed R2 URLs deliberately stay out so their
  // expiration cannot cause a refresh loop.
  const signature = JSON.stringify({
    jobs: (jobs || []).map((job) => [
      job.id,
      job.status,
      job.progress?.stage,
      job.progress?.published,
      job.progress?.detail,
      job.finished_at,
    ]),
    clips: (clips || []).map((clip) => [
      clip.id, clip.job_id, clip.r2_key, clip.created_at,
    ]),
  });
  return NextResponse.json(
    { signature },
    { headers: { "Cache-Control": "no-store, max-age=0" } }
  );
}
