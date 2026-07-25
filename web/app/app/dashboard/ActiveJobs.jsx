"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
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
const RECENT_FAILURE_MS = 15 * 60e3;

export default function ActiveJobs() {
  const [jobs, setJobs] = useState([]);
  const published = useRef(new Map());
  const router = useRouter();

  useEffect(() => {
    const sb = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
    );
    let alive = true;
    const load = async () => {
      const { data } = await sb
        .from("jobs")
        .select("id, vod_url, status, progress, error, created_at, finished_at")
        .in("status", ["queued", "running", "failed"])
        .gte(
          "created_at",
          new Date(Date.now() - RECENT_FAILURE_MS).toISOString()
        )
        .order("created_at", { ascending: false });
      if (alive) {
        let refresh = false;
        const currentIds = new Set((data || []).map((job) => job.id));
        for (const id of published.current.keys()) {
          if (!currentIds.has(id)) {
            published.current.delete(id);
            refresh = true;
          }
        }
        for (const job of data || []) {
          const count = Number(job.progress?.published || 0);
          const previous = published.current.get(job.id);
          if (previous != null && previous !== count) refresh = true;
          published.current.set(job.id, count);
        }
        setJobs(data || []);
        if (refresh) router.refresh();
      }
    };
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, [router]);

  if (jobs.length === 0) return null;

  return (
    <div className="mb-10">
      <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wide mb-3">
        In progress
      </h2>
      {jobs.map((j) => {
        const editKind = j.progress?.kind;
        const stage = j.status === "queued" ? null : j.progress?.stage;
        const idx = stage != null ? (ORDER[stage] ?? 0) : -1;
        const failed = j.status === "failed";
        const requested = Number(
          j.progress?.requested ??
          j.progress?.settings_snapshot?.clips_per_stream ?? 0
        );
        const ready = Number(j.progress?.published || 0);
        return (
          <div key={j.id}
               className={`rounded-2xl p-5 mb-3 border bg-[#12121a] ${
                 failed ? "border-red-900/70" : "border-[#23233a]"
               }`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <span className="relative flex h-3 w-3">
                  {!failed && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#9146FF] opacity-60"></span>}
                  <span className={`relative inline-flex rounded-full h-3 w-3 ${
                    failed ? "bg-red-500" : "bg-[#9146FF]"
                  }`}></span>
                </span>
                <span className="font-bold">
                  {failed
                    ? "Processing stopped"
                    : editKind === "clip_source"
                    ? "Preparing clip editor"
                    : editKind === "clip_edit"
                      ? "Rendering your clip revision"
                  : j.status !== "queued"
                    ? "Clipping your stream"
                    : Date.now() - new Date(j.created_at).getTime() > 15 * 60e3
                      ? "Queue is backed up — your job is saved and will run"
                      : "Waiting for a worker..."}
                </span>
              </div>
              <a href={j.vod_url} target="_blank"
                 className="text-xs text-purple-300 hover:underline">
                {j.vod_url.replace("https://www.", "")}
              </a>
            </div>
            {failed ? (
              <div className="rounded-xl border border-red-900/50 bg-red-950/20 px-4 py-3">
                <p className="text-sm text-red-300">
                  {j.progress?.detail ||
                    String(j.error || "The worker stopped unexpectedly.")
                      .split("\n").filter(Boolean).pop()}
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  This message stays here for 15 minutes so a fast failure
                  cannot look like the job disappeared.
                </p>
              </div>
            ) : null}
            {!failed && !editKind && ready > 0 ? (
              <div className="mb-4 rounded-xl border border-green-900/60 bg-green-950/20 px-4 py-3">
                <p className="text-sm font-bold text-green-300">
                  {ready} {ready === 1 ? "clip is" : "clips are"} ready
                </p>
                <p className="mt-0.5 text-xs text-gray-400">
                  You can watch and edit {ready === 1 ? "it" : "them"} below.
                  {requested > ready
                    ? ` The other ${requested - ready} ${
                        requested - ready === 1 ? "clip is" : "clips are"
                      } still loading.`
                    : " Finalizing the batch…"}
                </p>
              </div>
            ) : null}
            {!failed && editKind ? (
              <p className="text-sm text-gray-400">
                {j.status === "queued" ? "Waiting for the render worker…" :
                  editKind === "clip_source"
                    ? "Downloading editable source footage…"
                    : "Applying timeline cuts, captions, and media QA…"}
              </p>
            ) : !failed ? <ol className="space-y-1.5">
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
            </ol> : null}
          </div>
        );
      })}
    </div>
  );
}
