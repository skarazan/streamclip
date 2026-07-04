import { NextResponse } from "next/server";
import { serverClient } from "../../../lib/supabase";

export async function POST(request) {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await request.json();
  const n = Math.round(Number(body.clips_per_stream));
  if (!(n >= 1 && n <= 5)) {
    return NextResponse.json({ error: "clips_per_stream must be 1-5" }, { status: 400 });
  }

  // service key server-side: user-editable columns only, never credits/plan
  const r = await fetch(
    `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/users?id=eq.${user.id}`,
    {
      method: "PATCH",
      headers: {
        apikey: process.env.SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ clips_per_stream: n }),
    }
  );
  if (!r.ok) return NextResponse.json({ error: "update failed" }, { status: 500 });
  return NextResponse.json({ ok: true, clips_per_stream: n });
}
