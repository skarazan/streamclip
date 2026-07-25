"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const CLIP_COUNT_STORAGE_KEY = "streamclip.clips_per_stream";

export default function RunAgain({ vodUrl }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  const run = async () => {
    setBusy(true);
    setError("");
    const r = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        vod_url: vodUrl,
        clips_per_stream: Number(
          localStorage.getItem(CLIP_COUNT_STORAGE_KEY)
        ),
      }),
    }).catch(() => null);
    if (!r?.ok) {
      const data = await r?.json().catch(() => ({}));
      setError(data?.error || "Couldn’t queue this VOD.");
    } else {
      router.refresh();
    }
    setBusy(false);
  };

  return (
    <div className="flex items-center gap-2">
      {error && <span className="text-[10px] text-red-400 max-w-48">{error}</span>}
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className="text-xs font-bold rounded-lg border border-[#343451] px-3 py-1.5 text-gray-300 hover:border-[#9146FF] hover:text-white disabled:opacity-50"
      >
        {busy ? "Queuing…" : "Run again"}
      </button>
    </div>
  );
}
