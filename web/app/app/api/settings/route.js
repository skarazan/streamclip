import { NextResponse } from "next/server";
import { serverClient } from "../../../lib/supabase";
import { STYLE_PRESETS } from "../../../lib/stylePresets";
import { OPENING_EFFECTS, TITLE_STRATEGIES } from "../../../lib/contentPresets";

export async function POST(request) {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await request.json();

  // Fetch once so independent template controls merge instead of erasing one
  // another. The previous endpoint replaced the entire JSON profile whenever
  // caption style changed.
  const rows = await fetch(
    `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/users?id=eq.${user.id}&select=style_profile`,
    {
      headers: {
        apikey: process.env.SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
      },
      cache: "no-store",
    }
  ).then((r) => r.json());
  const profile = { ...(rows?.[0]?.style_profile || {}) };

  // service key server-side: user-editable columns only, never credits/plan
  const patch = {};
  if ("clips_per_stream" in body) {
    const n = Math.round(Number(body.clips_per_stream));
    if (!(n >= 1 && n <= 8)) {
      return NextResponse.json({ error: "clips_per_stream must be 1-8" }, { status: 400 });
    }
    patch.clips_per_stream = n;
  }
  if ("style_preset" in body) {
    // presets are server-defined — clients pick a name, never raw style JSON
    const preset = STYLE_PRESETS[body.style_preset];
    if (!preset) {
      return NextResponse.json({ error: "unknown style preset" }, { status: 400 });
    }
    // Replace renderer keys owned by the old caption preset, while retaining
    // packaging controls. This prevents stale font/box keys leaking between
    // caption presets.
    const packaging = {
      title_strategy: profile.title_strategy || "curiosity",
      opening_effect: profile.opening_effect || "punch_zoom",
    };
    patch.style_profile = { ...preset.style, ...packaging, preset: body.style_preset };
  }
  if ("title_strategy" in body) {
    if (!TITLE_STRATEGIES[body.title_strategy]) {
      return NextResponse.json({ error: "unknown title strategy" }, { status: 400 });
    }
    patch.style_profile = {
      ...(patch.style_profile || profile),
      title_strategy: body.title_strategy,
    };
  }
  if ("opening_effect" in body) {
    if (!OPENING_EFFECTS[body.opening_effect]) {
      return NextResponse.json({ error: "unknown opening effect" }, { status: 400 });
    }
    patch.style_profile = {
      ...(patch.style_profile || profile),
      opening_effect: body.opening_effect,
    };
  }
  if ("notification_email" in body) {
    if (typeof body.notification_email !== "boolean") {
      return NextResponse.json({ error: "notification_email must be boolean" }, { status: 400 });
    }
    patch.notification_email = body.notification_email;
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
