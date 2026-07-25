import { NextResponse } from "next/server";
import { serverClient } from "../../../../lib/supabase";
import { rest, serviceHeaders } from "../../../../lib/editJobs";

export async function GET(_request, { params }) {
  const sb = await serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await params;
  const rows = await fetch(
    rest(`/jobs?id=eq.${id}&user_id=eq.${user.id}&select=id,status,error,progress`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((r) => r.json());
  const job = rows?.[0];
  if (!job) return NextResponse.json({ error: "job not found" }, { status: 404 });
  const key = job.progress?.proxy_key || job.progress?.r2_key;
  // Keep editor playback same-origin. Some browsers stall when seeking a
  // cross-origin presigned R2 object even though the object itself is valid.
  // The media route preserves HTTP byte ranges, so seeking remains instant.
  const url = key ? `/api/edit-jobs/${job.id}/media` : null;
  return NextResponse.json({ ...job, url });
}
