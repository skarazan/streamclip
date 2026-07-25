import { NextResponse } from "next/server";
import { serverClient } from "../../../lib/supabase";
import { rest, serviceHeaders } from "../../../lib/editJobs";

export async function POST(request) {
  const sb = await serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const body = await request.json().catch(() => ({}));
  if (body.action === "cancel_deletion") {
    const response = await fetch(rest(`/users?id=eq.${user.id}`), {
      method: "PATCH",
      headers: serviceHeaders(),
      body: JSON.stringify({ deletion_requested_at: null }),
    });
    return response.ok
      ? NextResponse.json({ ok: true, deletion_requested_at: null })
      : NextResponse.json({ error: "Could not cancel deletion." }, { status: 500 });
  }
  if (body.action !== "schedule_deletion" || body.confirmation !== "DELETE") {
    return NextResponse.json(
      { error: "Type DELETE to schedule account deletion." },
      { status: 400 }
    );
  }
  const deletionAt = new Date(Date.now() + 7 * 24 * 60 * 60_000).toISOString();
  const response = await fetch(rest(`/users?id=eq.${user.id}`), {
    method: "PATCH",
    headers: serviceHeaders(),
    body: JSON.stringify({ deletion_requested_at: deletionAt, auto_clip: false }),
  });
  if (!response.ok) {
    return NextResponse.json({ error: "Could not schedule deletion." }, { status: 500 });
  }
  return NextResponse.json({ ok: true, deletion_requested_at: deletionAt });
}
