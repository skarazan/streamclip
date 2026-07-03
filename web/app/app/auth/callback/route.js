import { NextResponse } from "next/server";
import { serverClient } from "../../../lib/supabase";

export async function GET(request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  if (code) {
    const sb = serverClient();
    const { data, error } = await sb.auth.exchangeCodeForSession(code);
    if (!error && data?.user) {
      // first login: create the app-level user row (service key bypasses RLS)
      const meta = data.user.user_metadata || {};
      await fetch(`${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/users`, {
        method: "POST",
        headers: {
          apikey: process.env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
          "Content-Type": "application/json",
          Prefer: "resolution=ignore-duplicates",
        },
        body: JSON.stringify({
          id: data.user.id,
          twitch_id: meta.provider_id || meta.sub || data.user.id,
          twitch_login: meta.nickname || meta.name || "unknown",
        }),
      });
    }
  }
  return NextResponse.redirect(new URL("/dashboard", url.origin));
}
