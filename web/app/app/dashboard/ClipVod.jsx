"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const CLIP_COUNT_STORAGE_KEY = "streamclip.clips_per_stream";

export default function ClipVod({ titleStrategy, openingEffect }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const r = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Snapshot the visible picker value into the job itself. This avoids
        // a fast "pick 8, then run" click racing the background settings save.
        body: JSON.stringify({
          vod_url: url,
          clips_per_stream: Number(
            localStorage.getItem(CLIP_COUNT_STORAGE_KEY)
          ),
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        setError(data.error || "something went wrong — try again");
      } else {
        setUrl("");
        router.refresh(); // ActiveJobs also polls; this makes it instant
      }
    } catch {
      setError("network error — try again");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl p-5 mb-10 border border-[#23233a] bg-[#12121a]">
      <div className="flex flex-wrap gap-2 mb-3 text-[10px] font-black uppercase tracking-wide">
        <span className="rounded-full border border-[#2e2e4a] px-2.5 py-1 text-purple-300">
          Title · {String(titleStrategy).replace("_", " ")}
        </span>
        <span className="rounded-full border border-[#2e2e4a] px-2.5 py-1 text-purple-300">
          Open · {String(openingEffect).replace("_", " ")}
        </span>
      </div>
      <form onSubmit={submit} className="flex flex-col sm:flex-row gap-3">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Paste a Twitch VOD link — twitch.tv/videos/…"
          className="flex-1 rounded-xl bg-[#0c0c13] border border-[#2e2e4a] px-4 py-3 text-sm placeholder-gray-500 focus:outline-none focus:border-[#9146FF]"
          required
        />
        <button
          type="submit"
          disabled={busy || !url.trim()}
          className="shrink-0 bg-[#9146FF] hover:bg-[#7a2ff0] disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold px-6 py-3 rounded-xl text-sm"
        >
          {busy ? "Queuing…" : "⚡ Clip this VOD"}
        </button>
      </form>
      <p className="text-xs text-gray-500 mt-2">
        1 GW per stream (2 for streams over 8h). Your channel&apos;s VODs only.
      </p>
      {error && <p className="text-sm text-red-400 mt-2">{error}</p>}
    </div>
  );
}
