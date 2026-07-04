"use client";

import { useEffect, useState } from "react";
import { createBrowserClient } from "@supabase/ssr";

const STAGES = [
  ["finding_vod", "Finding your VOD"],
  ["downloading_audio", "Downloading stream audio"],
  ["transcribing", "Transcribing (AI listens to the whole stream)"],
  ["scoring", "Hunting for funny moments"],
  ["clipping", "Cutting the winners"],
  ["rendering", "Captions + vertical layout"],
  ["uploading", "Delivering clips"],
];
const ORDER = Object.fromEntries(STAGES.map(([k], i) => [k, i]));
const LABEL = Object.fromEntries(STAGES);

export default function ActiveJobs() {
  const [jobs, setJobs] = useState([]);

  useEffect(() => {
    const sb = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
    );
    let alive = true;
    const load = async () => {
      const { data } = await sb
        .from("jobs")
        .select("id, vod_url, status, progress, created_at")
        .in("status", ["queued", "running"])
        .order("created_at", { ascending: false });
      if (alive) setJobs(data || []);
    };
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (jobs.length === 0) return null;

  return (
    <div className="mb-10">
      <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wide mb-3">
        In progress
      </h2>
      {jobs.map((j) => {
        const stage = j.status === "queued" ? null : j.progress?.stage;
        const idx = stage != null ? (ORDER[stage] ?? 0) : -1;
        return (
          <div key={j.id}
               className="rounded-2xl p-5 mb-3 border border-[#23233a] bg-[#12121a]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#9146FF] opacity-60"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-[#9146FF]"></span>
                </span>
                <span className="font-bold">
                  {j.status === "queued" ? "Waiting for a worker..." : "Clipping your stream"}
                </span>
              </div>
              <a href={j.vod_url} target="_blank"
                 className="text-xs text-purple-300 hover:underline">
                {j.vod_url.replace("https://www.", "")}
              </a>
            </div>
            <ol className="space-y-1.5">
              {STAGES.map(([key, label], i) => (
                <li key={key} className="flex items-center gap-2 text-sm">
                  <span>{i < idx ? "✅" : i === idx ? "🔄" : "◽"}</span>
                  <span className={i === idx ? "text-white font-semibold"
                                  : i < idx ? "text-gray-400" : "text-gray-600"}>
                    {label}
                    {i === idx && j.progress?.detail ? (
                      <span className="text-gray-400 font-normal"> — {j.progress.detail}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        );
      })}
    </div>
  );
}
