import { NextResponse } from "next/server";
import { serverClient } from "../../../lib/supabase";
import { STYLE_PRESETS } from "../../../lib/stylePresets";

export async function POST(request) {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await request.json();

  // service key server-side: user-editable columns only, never credits/plan
  const patch = {};
  if ("clips_per_stream" in body) {
    const n = Math.round(Number(body.clips_per_stream));
    if (!(n >= 1 && n <= 5)) {
      return NextResponse.json({ error: "clips_per_stream must be 1-5" }, { status: 400 });
    }
    patch.clips_per_stream = n;
  }
  if ("style_preset" in body) {
    // presets are server-defined — clients pick a name, never raw style JSON
    const preset = STYLE_PRESETS[body.style_preset];
    if (!preset) {
      return NextResponse.json({ error: "unknown style preset" }, { status: 400 });
    }
    patch.style_profile = { ...preset.style, preset: body.style_preset };
  }
  if (Object.keys(patch).length === 0) {
    return NextResponse.json({ error: "nothing to update" }, { status: 400 });
  }

  const r = await fetch(
    `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/users?id=eq.${user.id}`,
    {
      method: "PATCH",
      headers: {
        apikey: process.env.SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(patch),
    }
  );
  if (!r.ok) return NextResponse.json({ error: "update failed" }, { status: 500 });
  return NextResponse.json({ ok: true, ...patch });
}
