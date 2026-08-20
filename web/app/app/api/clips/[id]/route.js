import { NextResponse } from "next/server";
import { serverClient } from "../../../../lib/supabase";

const headers = () => ({
  apikey: process.env.SUPABASE_SERVICE_KEY,
  Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
  "Content-Type": "application/json",
});

export async function PATCH(request, { params }) {
  const sb = await serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  const body = await request.json().catch(() => ({}));
  if ("feedback" in body) {
    const feedback = Number(body.feedback);
    if (![1, -1].includes(feedback)) {
      return NextResponse.json({ error: "feedback must be 1 or -1" }, { status: 400 });
    }
    const validReasons = new Set([
      "good_as_is", "weak_moment", "missing_context", "cause_not_visible",
      "slow_or_redundant", "starts_late", "ends_early", "bad_title",
      "bad_framing", "technical", "other",
    ]);
    const feedbackReason = String(body.feedback_reason || "").trim();
    if (!validReasons.has(feedbackReason)) {
      return NextResponse.json(
        { error: "choose a valid feedback reason" },
        { status: 400 }
      );
    }
    if (feedback === 1 && feedbackReason !== "good_as_is") {
      return NextResponse.json(
        { error: "positive feedback must use good_as_is" },
        { status: 400 }
      );
    }
    if (feedback === -1 && feedbackReason === "good_as_is") {
      return NextResponse.json(
        { error: "discarded clips need a failure reason" },
        { status: 400 }
      );
    }
    let feedbackResponse = await fetch(
      `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/clips?id=eq.${id}&user_id=eq.${user.id}`,
      {
        method: "PATCH",
        headers: { ...headers(), Prefer: "return=representation" },
        body: JSON.stringify({
          feedback,
          feedback_reason: feedbackReason,
          feedback_at: new Date().toISOString(),
        }),
      }
    );
    let reasonSaved = feedbackResponse.ok;
    if (!feedbackResponse.ok) {
      const detail = await feedbackResponse.text();
      // Additive migration bridge: keep thumbs usable while the founder
      // applies 20260819_quality_learning.sql. The response says the richer
      // reason was not persisted so callers never mistake fallback for data.
      if (detail.toLowerCase().includes("feedback_reason") ||
          detail.toLowerCase().includes("feedback_at")) {
        feedbackResponse = await fetch(
          `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/clips?id=eq.${id}&user_id=eq.${user.id}`,
          {
            method: "PATCH",
            headers: { ...headers(), Prefer: "return=representation" },
            body: JSON.stringify({ feedback }),
          }
        );
        reasonSaved = false;
      }
    }
    const rows = feedbackResponse.ok ? await feedbackResponse.json() : [];
    return rows.length
      ? NextResponse.json({
          ok: true,
          feedback,
          feedback_reason: feedbackReason,
          reason_saved: reasonSaved,
        })
      : NextResponse.json({ error: "clip not found" }, { status: 404 });
  }
  const title = String(body.title || "").trim();
  const hook = String(body.hook || "").trim();
  if (title.length < 4 || title.length > 100) {
    return NextResponse.json(
      { error: "title must be 4-100 characters" },
      { status: 400 }
    );
  }
  if (hook.length > 80) {
    return NextResponse.json(
      { error: "hook must be 80 characters or fewer" },
      { status: 400 }
    );
  }

  const r = await fetch(
    `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/clips?id=eq.${id}&user_id=eq.${user.id}`,
    {
      method: "PATCH",
      headers: { ...headers(), Prefer: "return=representation" },
      body: JSON.stringify({ title, hook }),
    }
  );
  if (!r.ok) {
    return NextResponse.json({ error: "update failed" }, { status: 500 });
  }
  const rows = await r.json();
  if (!rows.length) {
    return NextResponse.json({ error: "clip not found" }, { status: 404 });
  }
  return NextResponse.json({ ok: true, title, hook });
}
