"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function ClipVod() {
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
        body: JSON.stringify({ vod_url: url }),
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
