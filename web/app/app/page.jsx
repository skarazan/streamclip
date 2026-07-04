"use client";

import { createBrowserClient } from "@supabase/ssr";

export default function Home() {
  const login = async () => {
    const sb = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
    );
    await sb.auth.signInWithOAuth({
      provider: "twitch",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
  };

  return (
    <main className="max-w-3xl mx-auto px-6 pt-28 text-center">
      <p className="inline-block text-xs font-semibold px-3 py-1 rounded-full mb-6 text-purple-300 border border-[#2e2e4a] bg-[#15151f]">
        Built for Twitch gaming streamers
      </p>
      <h1 className="text-5xl md:text-6xl font-black leading-tight tracking-tight">
        You stream.<br />We clip. <span className="text-[#9146FF]">While you sleep.</span>
      </h1>
      <p className="mt-6 text-lg text-gray-400">
        A few hours after every stream, your funniest moments are scored,
        captioned vertical Shorts — styled like your channel, ready to post.
      </p>
      <button
        onClick={login}
        className="mt-10 inline-flex items-center gap-2 bg-[#9146FF] hover:bg-[#7a2ff0] text-white font-bold px-8 py-4 rounded-xl text-lg"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
          <path d="M11.571 4.714h1.715v5.143H11.57zm4.715 0H18v5.143h-1.714zM6 0L1.714 4.286v15.428h5.143V24l4.286-4.286h3.428L22.286 12V0zm14.571 11.143l-3.428 3.428h-3.429l-3 3v-3H6.857V1.714h13.714z" />
        </svg>
        Continue with Twitch
      </button>
      <p className="mt-4 text-xs text-gray-500">Free trial — 2 gigawatts, no card. ⚡</p>
    </main>
  );
}
