export async function ensureOfflineSubscription(broadcasterUserId) {
  const clientId = process.env.TWITCH_CLIENT_ID;
  const clientSecret = process.env.TWITCH_CLIENT_SECRET;
  const secret = process.env.TWITCH_EVENTSUB_SECRET;
  const callback = process.env.TWITCH_EVENTSUB_CALLBACK_URL;
  if (!clientId || !clientSecret || !secret || !callback || !broadcasterUserId) {
    return { configured: false };
  }
  const tokenResponse = await fetch("https://id.twitch.tv/oauth2/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: clientId,
      client_secret: clientSecret,
      grant_type: "client_credentials",
    }),
    cache: "no-store",
  });
  const tokenData = await tokenResponse.json();
  if (!tokenResponse.ok) throw new Error("Twitch app token failed");
  const response = await fetch("https://api.twitch.tv/helix/eventsub/subscriptions", {
    method: "POST",
    headers: {
      "Client-Id": clientId,
      Authorization: `Bearer ${tokenData.access_token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      type: "stream.offline",
      version: "1",
      condition: { broadcaster_user_id: String(broadcasterUserId) },
      transport: { method: "webhook", callback, secret },
    }),
  });
  // 409 means this exact subscription already exists and is healthy.
  if (!response.ok && response.status !== 409) {
    throw new Error("Twitch EventSub registration failed");
  }
  return { configured: true };
}
