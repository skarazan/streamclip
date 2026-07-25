"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { OPENING_EFFECTS, TITLE_STRATEGIES } from "../../../lib/contentPresets";
import { STYLE_PRESETS } from "../../../lib/stylePresets";

export default function OnboardingForm() {
  const [style, setStyle] = useState("classic");
  const [titleStrategy, setTitleStrategy] = useState("curiosity");
  const [opening, setOpening] = useState("punch_zoom");
  const [vod, setVod] = useState("");
  const [latestTitle, setLatestTitle] = useState("");
  const [finding, setFinding] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  useEffect(() => {
    fetch("/api/onboarding/latest-vod", { cache: "no-store" })
      .then(async (response) => {
        const data = await response.json();
        if (response.ok) {
          setVod(data.vod_url);
          setLatestTitle(data.title || "Latest finished VOD");
        } else {
          setError(data.error || "");
        }
      })
      .catch(() => setError("Paste your latest Twitch VOD below."))
      .finally(() => setFinding(false));
  }, []);

  const start = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    window.plausible?.("Onboarding Template Picked", {
      props: { style, title_strategy: titleStrategy, opening },
    });
    try {
      const settingBodies = [
        { style_preset: style },
        { title_strategy: titleStrategy },
        { opening_effect: opening },
      ];
      for (const body of settingBodies) {
        const response = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!response.ok) throw new Error("Template settings could not be saved.");
      }
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vod_url: vod, clips_per_stream: 5 }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "The first batch could not start.");
      window.plausible?.("First Job Enqueued");
      router.push("/app");
      router.refresh();
    } catch (startError) {
      setError(startError.message);
      setBusy(false);
    }
  };

  return (
    <form onSubmit={start} className="mt-10 space-y-8">
      <fieldset>
        <legend className="font-black">1. Caption style</legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {Object.entries(STYLE_PRESETS).map(([key, value]) => (
            <button type="button" key={key} onClick={() => setStyle(key)}
              className={`rounded-xl border p-4 text-left ${style === key ? "border-[#9146FF] bg-purple-950/20" : "border-[#2b2b43] bg-[#12121a]"}`}>
              <span className="font-black">{value.label}</span>
              <span className="mt-1 block text-xs text-gray-500">{value.desc}</span>
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend className="font-black">2. Hook strategy</legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {Object.entries(TITLE_STRATEGIES).map(([key, value]) => (
            <button type="button" key={key} onClick={() => setTitleStrategy(key)}
              className={`rounded-xl border p-4 text-left ${titleStrategy === key ? "border-[#9146FF] bg-purple-950/20" : "border-[#2b2b43] bg-[#12121a]"}`}>
              <span className="font-black">{value.label}</span>
              <span className="mt-1 block text-xs text-gray-500">{value.desc}</span>
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend className="font-black">3. Opening motion</legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {Object.entries(OPENING_EFFECTS).map(([key, value]) => (
            <button type="button" key={key} onClick={() => setOpening(key)}
              className={`rounded-xl border p-4 text-left ${opening === key ? "border-[#9146FF] bg-purple-950/20" : "border-[#2b2b43] bg-[#12121a]"}`}>
              <span className="font-black">{value.glyph} {value.label}</span>
              <span className="mt-1 block text-xs text-gray-500">{value.desc}</span>
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend className="font-black">4. First stream</legend>
        <p className="mt-2 text-sm text-gray-400">
          {finding ? "Finding your latest finished VOD…" : latestTitle || "Paste a finished VOD from your channel."}
        </p>
        <input type="url" required value={vod} onChange={(event) => setVod(event.target.value)}
          placeholder="https://www.twitch.tv/videos/…"
          className="mt-3 w-full rounded-xl border border-[#2e2e4a] bg-[#0c0c13] px-4 py-3" />
      </fieldset>
      {error && <p className="rounded-xl border border-amber-800/50 bg-amber-950/20 p-3 text-sm text-amber-200">{error}</p>}
      <button disabled={busy || finding || !vod} className="w-full rounded-xl bg-[#9146FF] px-6 py-4 text-lg font-black disabled:opacity-60">
        {busy ? "Starting your first batch…" : "Start my first batch"}
      </button>
    </form>
  );
}
