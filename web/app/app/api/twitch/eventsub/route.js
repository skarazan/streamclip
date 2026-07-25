import crypto from "node:crypto";
import { NextResponse } from "next/server";
import { rest, serviceHeaders } from "../../../../lib/editJobs";

function validSignature(raw, headers) {
  const secret = process.env.TWITCH_EVENTSUB_SECRET;
  const id = headers.get("twitch-eventsub-message-id");
  const timestamp = headers.get("twitch-eventsub-message-timestamp");
  const provided = headers.get("twitch-eventsub-message-signature") || "";
  if (!secret || !id || !timestamp) return false;
  if (Math.abs(Date.now() - new Date(timestamp).getTime()) > 10 * 60_000) {
    return false;
  }
  const expected = `sha256=${crypto
    .createHmac("sha256", secret)
    .update(id + timestamp + raw)
    .digest("hex")}`;
  if (expected.length !== provided.length) return false;
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(provided));
}

export async function POST(request) {
  const raw = await request.text();
  if (!validSignature(raw, request.headers)) {
    return NextResponse.json({ error: "invalid signature" }, { status: 403 });
  }
  const payload = JSON.parse(raw);
  const type = request.headers.get("twitch-eventsub-message-type");
  if (type === "webhook_callback_verification") {
    return new Response(payload.challenge, {
      status: 200,
      headers: { "Content-Type": "text/plain" },
    });
  }
  if (type === "revocation") {
    console.error("Twitch EventSub revoked", payload.subscription);
    return new Response(null, { status: 204 });
  }
  const event = payload.event;
  if (
    type !== "notification" ||
    payload.subscription?.type !== "stream.offline" ||
    !event?.broadcaster_user_id
  ) {
    return new Response(null, { status: 204 });
  }
  const users = await fetch(
    rest(`/users?twitch_id=eq.${encodeURIComponent(event.broadcaster_user_id)}&auto_clip=eq.true&deletion_requested_at=is.null&select=id,credits`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((response) => response.json());
  const user = users?.[0];
  if (!user || user.credits < 1) return new Response(null, { status: 204 });

  const eventId = request.headers.get("twitch-eventsub-message-id");
  const duplicate = await fetch(
    rest(`/jobs?progress-%3E%3Eeventsub_id=eq.${encodeURIComponent(eventId)}&select=id&limit=1`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((response) => response.json());
  if (duplicate?.length) return new Response(null, { status: 204 });
  const runAfter = new Date(Date.now() + 10 * 60_000).toISOString();
  await fetch(rest("/jobs"), {
    method: "POST",
    headers: serviceHeaders(),
    body: JSON.stringify({
      user_id: user.id,
      vod_url: `twitch://latest/${event.broadcaster_user_id}`,
      status: "queued",
      run_after: runAfter,
      progress: {
        stage: "finding_vod",
        version: "pending",
        auto_trigger: true,
        eventsub_id: eventId,
        detail: "stream ended — waiting for the Twitch archive",
      },
    }),
  });
  return new Response(null, { status: 204 });
}
