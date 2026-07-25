import { NextResponse } from "next/server";
import { serverClient } from "../../../../lib/supabase";

const headers = () => ({
  apikey: process.env.SUPABASE_SERVICE_KEY,
  Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
  "Content-Type": "application/json",
});

export async function PATCH(request, { params }) {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await request.json().catch(() => ({}));
  if ("feedback" in body) {
    const feedback = Number(body.feedback);
    if (![1, -1].includes(feedback)) {
      return NextResponse.json({ error: "feedback must be 1 or -1" }, { status: 400 });
    }
    const feedbackResponse = await fetch(
      `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/clips?id=eq.${params.id}&user_id=eq.${user.id}`,
      {
        method: "PATCH",
        headers: { ...headers(), Prefer: "return=representation" },
        body: JSON.stringify({ feedback }),
      }
    );
    const rows = feedbackResponse.ok ? await feedbackResponse.json() : [];
    return rows.length
      ? NextResponse.json({ ok: true, feedback })
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
    `${process.env.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/clips?id=eq.${params.id}&user_id=eq.${user.id}`,
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
