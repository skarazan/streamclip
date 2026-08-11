"use client";

import { useEffect, useState } from "react";

// The object this URL points at, ignoring the presigned query string. Same
// object + new signature is churn; a different object is a different clip.
const objectOf = (url) => String(url || "").split("?")[0];

// Click-to-load player. A mounted <video> holds decoder + network buffers
// (~100MB each in Chromium); a grid of always-mounted players was eating
// >1GB. Nothing loads until the user asks; closing releases it again.
export default function ClipPlayer({ src, title }) {
  // The URL is captured when the user presses play, because the dashboard
  // mints a fresh presigned R2 URL on every server render and
  // DashboardAutoRefresh re-renders whenever job progress changes — a
  // playing clip had its `src` swapped every few seconds and reloaded
  // mid-playback.
  const [playing, setPlaying] = useState(null);

  // ...but pinning the URL outright meant an exported revision never
  // appeared: the clip row pointed at the new file while the open player
  // kept showing the old one, reported as "im still seeing the same thing
  // not my version". Follow a change of OBJECT, ignore a change of
  // signature.
  useEffect(() => {
    setPlaying((current) =>
      current && objectOf(current) !== objectOf(src) ? src : current);
  }, [src]);

  if (!playing) {
    return (
      <button
        type="button"
        onClick={() => setPlaying(src)}
        className="group relative block w-full aspect-[9/16] overflow-hidden rounded-xl bg-gradient-to-b from-[#1b1b2b] via-[#101018] to-black"
        aria-label={`Play ${title || "clip"}`}
      >
        <span className="absolute inset-0 flex flex-col items-center justify-center gap-3">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-[#9146FF]/90 shadow-lg shadow-purple-950/50 transition-transform group-hover:scale-110">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="white" aria-hidden="true">
              <path d="M8 5v14l11-7z" />
            </svg>
          </span>
          <span className="px-4 text-center text-xs font-bold text-gray-400">
            {title || "Preview clip"}
          </span>
        </span>
      </button>
    );
  }

  return (
    <div className="relative">
      <video
        src={playing}
        controls
        autoPlay
        playsInline
        preload="auto"
        className="rounded-xl w-full aspect-[9/16] object-cover bg-black"
      />
      <button
        type="button"
        onClick={() => setPlaying(null)}
        className="absolute right-2 top-2 z-10 rounded-full bg-black/70 px-2 py-0.5 text-xs font-bold text-gray-300 hover:text-white"
        aria-label="Close preview"
      >
        ✕
      </button>
    </div>
  );
}
