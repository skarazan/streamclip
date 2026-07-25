import { NextResponse } from "next/server";
import { serverClient } from "../../../lib/supabase";
import { ensureOfflineSubscription } from "../../../lib/twitchEventSub";

export async function GET(request) {
  const url = new URL(request.url);
  if (url.searchParams.get("error")) {
    return NextResponse.redirect(new URL("/login?error=oauth_denied", url.origin));
  }
  const code = url.searchParams.get("code");
  if (code) {
    const sb = await serverClient();
    const { data, error } = await sb.auth.exchangeCodeForSession(code);
    if (error || !data?.user) {
      return NextResponse.redirect(new URL("/login?error=session_failed", url.origin));
    }
    if (data.user) {
      // first login: create the app-level user row (service key bypasses RLS)
      const meta = data.user.user_metadata || {};
      const existing = await fetch(
        `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/users?id=eq.${data.user.id}&select=id`,
        {
          headers: {
            apikey: process.env.SUPABASE_SERVICE_KEY,
            Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
          },
          cache: "no-store",
        }
      ).then((response) => response.json());
      const firstLogin = !existing?.length;
      let profileResponse = await fetch(`${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/users`, {
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
          email: data.user.email || null,
        }),
      });
      if (!profileResponse.ok) {
        // The app may deploy immediately before the additive email migration.
        profileResponse = await fetch(
          `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/users`,
          {
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
          }
        );
      }
      if (data.user.email) {
        await fetch(
          `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/users?id=eq.${data.user.id}`,
          {
            method: "PATCH",
            headers: {
              apikey: process.env.SUPABASE_SERVICE_KEY,
              Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ email: data.user.email }),
          }
        );
      }
      try {
        await ensureOfflineSubscription(
          meta.provider_id || meta.sub || data.user.id
        );
      } catch (subscriptionError) {
        console.error("EventSub registration warning", subscriptionError);
      }
      return NextResponse.redirect(
        new URL(firstLogin ? "/app/onboarding" : "/app", url.origin)
      );
    }
  }
  return NextResponse.redirect(new URL("/login?error=session_failed", url.origin));
}
