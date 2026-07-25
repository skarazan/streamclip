"use client";

import { createBrowserClient } from "@supabase/ssr";
import { useState } from "react";

export default function TwitchLoginButton({
  children = "Continue with Twitch",
  redirect = "/auth/callback",
  className = "",
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const login = async () => {
    setBusy(true);
    setError("");
    window.plausible?.("OAuth Started");
    const sb = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
    );
    const { error: authError } = await sb.auth.signInWithOAuth({
      provider: "twitch",
      options: { redirectTo: `${window.location.origin}${redirect}` },
    });
    if (authError) {
      setError("Twitch sign-in could not start. Please try again.");
      setBusy(false);
    }
  };
  return (
    <div>
      <button
        type="button"
        onClick={login}
        disabled={busy}
        className={`inline-flex items-center justify-center gap-2 rounded-xl bg-[#9146FF] px-6 py-3 font-black text-white hover:bg-[#7a2ff0] disabled:opacity-60 ${className}`}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M11.571 4.714h1.715v5.143H11.57zm4.715 0H18v5.143h-1.714zM6 0L1.714 4.286v15.428h5.143V24l4.286-4.286h3.428L22.286 12V0zm14.571 11.143l-3.428 3.428h-3.429l-3 3v-3H6.857V1.714h13.714z" />
        </svg>
        {busy ? "Connecting…" : children}
      </button>
      {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
    </div>
  );
}
