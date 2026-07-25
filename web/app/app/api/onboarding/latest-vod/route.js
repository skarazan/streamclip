import { NextResponse } from "next/server";
import { serverClient } from "../../../../lib/supabase";

export async function GET() {
  const sb = await serverClient();
  const { data: { session } } = await sb.auth.getSession();
  const user = session?.user;
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const twitchUserId =
    user.user_metadata?.provider_id ||
    user.user_metadata?.sub ||
    user.identities?.find((identity) => identity.provider === "twitch")?.identity_data?.provider_id;
  if (!session.provider_token || !twitchUserId || !process.env.TWITCH_CLIENT_ID) {
    return NextResponse.json(
      { error: "Paste your latest Twitch VOD to start the first batch." },
      { status: 409 }
    );
  }
  const response = await fetch(
    `https://api.twitch.tv/helix/videos?user_id=${encodeURIComponent(twitchUserId)}&type=archive&first=1`,
    {
      headers: {
        "Client-Id": process.env.TWITCH_CLIENT_ID,
        Authorization: `Bearer ${session.provider_token}`,
      },
      cache: "no-store",
    }
  );
  const data = await response.json().catch(() => ({}));
  const video = data?.data?.[0];
  if (!response.ok || !video?.id) {
    return NextResponse.json(
      { error: "No finished Twitch VOD was found. You can paste one below." },
      { status: 404 }
    );
  }
  return NextResponse.json({
    vod_url: `https://www.twitch.tv/videos/${video.id}`,
    title: video.title,
    created_at: video.created_at,
  });
}
