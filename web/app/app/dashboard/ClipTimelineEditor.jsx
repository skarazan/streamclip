"use client";

import { useEffect, useRef, useState } from "react";
import EditableTimeline from "./EditableTimeline";

const round = (n) => Math.round(n * 10) / 10;

function subtractCuts(start, end, cuts) {
  const sorted = cuts
    .map(([a, b]) => [Math.max(start, a), Math.min(end, b)])
    .filter(([a, b]) => b > a)
    .sort((a, b) => a[0] - b[0]);
  const keep = [];
  let cursor = start;
  for (const [a, b] of sorted) {
    if (a > cursor) keep.push([round(cursor), round(a)]);
    cursor = Math.max(cursor, b);
  }
  if (cursor < end) keep.push([round(cursor), round(end)]);
  return keep;
}

function recipeCuts(recipe) {
  const keep = recipe.keep_intervals || [[recipe.source_start, recipe.source_end]];
  const cuts = [];
  let cursor = Number(recipe.source_start);
  for (const [a, b] of keep) {
    if (Number(a) > cursor) cuts.push([cursor, Number(a)]);
    cursor = Math.max(cursor, Number(b));
  }
  if (cursor < Number(recipe.source_end)) cuts.push([cursor, Number(recipe.source_end)]);
  return cuts;
}

function nextPlayable(at, cuts, end) {
  let next = Number(at);
  for (const [a, b] of [...cuts].sort((x, y) => x[0] - y[0])) {
    if (next >= a - .02 && next < b - .05) next = b + .01;
  }
  return Math.min(Number(end), next);
}

export default function ClipTimelineEditor({ clipId }) {
  const video = useRef(null);
  const previewingEdit = useRef(true);
  const [open, setOpen] = useState(false);
  const [sourceJob, setSourceJob] = useState("");
  const [source, setSource] = useState(null);
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [buffering, setBuffering] = useState(false);
  const [mediaError, setMediaError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [playerMode, setPlayerMode] = useState("edit");
  const [cuts, setCuts] = useState([]);
  const [message, setMessage] = useState("");

  const seekTo = (absolute, inspectSource = true) => {
    const el = video.current;
    if (!el || !source) return;
    const next = Math.max(source.lo, Math.min(source.hi, Number(absolute)));
    if (inspectSource) {
      previewingEdit.current = false;
      setPlayerMode("source");
    }
    el.currentTime = next - source.lo;
    setPlayhead(next);
  };

  const play = async () => {
    const el = video.current;
    if (!el) return;
    try {
      setBuffering(el.readyState < 3);
      setMediaError("");
      await el.play();
      setMessage("");
    } catch (error) {
      setBuffering(false);
      setMediaError(
        error?.name === "NotAllowedError"
          ? "Playback was blocked. Press play again."
          : "The preview could not start. Retry it below."
      );
    }
  };

  const retryPreview = () => {
    const el = video.current;
    if (!el) return;
    setMediaError("");
    setBuffering(true);
    el.load();
  };

  const togglePlayback = () => {
    const el = video.current;
    if (!el) return;
    if (el.paused) {
      // Play always previews the actual edit. Paused scrubbing may inspect a
      // red range, but once playback starts that range must be skipped.
      previewingEdit.current = true;
      setPlayerMode("edit");
      if (source) {
        const absolute = source.lo + el.currentTime;
        const target = absolute < start || absolute >= end - .05
          ? nextPlayable(start, cuts, end)
          : nextPlayable(absolute, cuts, end);
        if (Math.abs(target - absolute) > .02) seekTo(target, false);
      }
      play();
    } else {
      el.pause();
    }
  };

  const playEdit = () => {
    previewingEdit.current = true;
    setPlayerMode("edit");
    seekTo(nextPlayable(start, cuts, end), false);
    play();
  };

  // The proxy is continuous. Only "Preview edit" interprets the cut recipe.
  // Paused/raw-source scrubbing must never fight the user's playhead.
  useEffect(() => {
    const el = video.current;
    if (!el || !source) return undefined;
    let frameId;
    let stopped = false;
    let lastUiUpdate = 0;
    const checkPlayhead = (now = 0) => {
      if (stopped) return;
      const absolute = source.lo + el.currentTime;
      // Updating React on every decoded frame makes the controls compete with
      // playback. Ten UI updates/second remains visually smooth.
      if (!now || now - lastUiUpdate >= 100) {
        setPlayhead(absolute);
        lastUiUpdate = now;
      }
      if (!el.paused && previewingEdit.current) {
        if (absolute < start - .05) {
          el.currentTime = Math.max(
            0, nextPlayable(start, cuts, end) - source.lo);
        }
        const playable = nextPlayable(absolute, cuts, end);
        if (playable > absolute + .02) {
          el.currentTime = playable - source.lo;
        } else if (absolute >= end - .03) {
          el.pause();
        }
      }
      if (el.requestVideoFrameCallback) {
        frameId = el.requestVideoFrameCallback(checkPlayhead);
      }
    };
    const onTimeUpdate = () => {
      if (!el.requestVideoFrameCallback) checkPlayhead();
    };
    el.addEventListener("timeupdate", onTimeUpdate);
    if (el.requestVideoFrameCallback) {
      frameId = el.requestVideoFrameCallback(checkPlayhead);
    }
    return () => {
      stopped = true;
      el.removeEventListener("timeupdate", onTimeUpdate);
      if (frameId != null && el.cancelVideoFrameCallback) {
        el.cancelVideoFrameCallback(frameId);
      }
    };
  }, [source, start, end, cuts]);

  useEffect(() => {
    const el = video.current;
    if (!el || !source) return undefined;
    const initialize = () => {
      const firstFrame = nextPlayable(start, cuts, end);
      el.currentTime = Math.max(0, firstFrame - source.lo);
      setPlayhead(firstFrame);
    };
    el.addEventListener("loadedmetadata", initialize);
    if (el.readyState >= 1) initialize();
    return () => el.removeEventListener("loadedmetadata", initialize);
    // This is source initialization, not a reaction to timeline adjustments.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source]);

  const onPlayerKeyDown = (event) => {
    if (event.key === " ") {
      event.preventDefault();
      togglePlayback();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      seekTo(playhead - 5);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      seekTo(playhead + 5);
    }
  };

  const formatTime = (seconds) => {
    const safe = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(safe / 60);
    const rest = safe - minutes * 60;
    return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
  };

  const poll = async (jobId, rendering = false) => {
    for (;;) {
      const r = await fetch(`/api/edit-jobs/${jobId}`, { cache: "no-store" });
      const data = await r.json().catch(() => ({}));
      if (data.status === "failed") throw new Error(data.error || "render failed");
      if (data.status === "done") {
        if (rendering) {
          setMessage("Revision ready. Refreshing…");
          window.location.reload();
          return;
        }
        const p = data.progress;
        if (!data.url) throw new Error("Preview file is not available yet.");
        setBuffering(true);
        setMediaError("");
        setSource({
          url: data.url,
          lo: Number(p.source_start),
          hi: Number(p.source_end),
          waveform: Array.isArray(p.waveform) ? p.waveform : [],
        });
        setStart(Number(p.recipe.source_start));
        setEnd(Number(p.recipe.source_end));
        setPlayhead(Number(p.recipe.source_start));
        previewingEdit.current = true;
        setPlayerMode("edit");
        setCuts(recipeCuts(p.recipe));
        setMessage("");
        return;
      }
      setMessage(rendering ? "Rendering revision…" : "Preparing editable source…");
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  };

  const launch = async () => {
    setOpen(true);
    setMessage("Preparing editable source…");
    const r = await fetch(`/api/clips/${clipId}/editor-source`, { method: "POST" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setMessage(data.error || "Couldn’t open editor");
      return;
    }
    setSourceJob(data.job_id);
    try {
      await poll(data.job_id);
    } catch (error) {
      setMessage(error.message);
    }
  };

  const renderRevision = async () => {
    if (exporting) return;
    const keep = subtractCuts(start, end, cuts);
    setExporting(true);
    // Show what is actually being sent. Three consecutive exports produced
    // byte-identical recipes while the timeline appeared edited, and there
    // was no way to tell from the UI whether the drag had reached this
    // state or the render was ignoring it. The numbers here are the payload.
    setMessage(
      `Queuing ${keep.reduce((t, [a, b]) => t + (b - a), 0).toFixed(1)}s`
      + ` from ${start.toFixed(1)}–${end.toFixed(1)}`
      + ` (${keep.length} piece${keep.length === 1 ? "" : "s"})…`);
    const r = await fetch(`/api/clips/${clipId}/revisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_job_id: sourceJob, source_start: start, source_end: end,
        keep_intervals: keep,
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setMessage(data.error || "Couldn’t render revision");
      setExporting(false);
      return;
    }
    try {
      await poll(data.job_id, true);
    } catch (error) {
      setMessage(error.message);
      setExporting(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={launch}
        className="w-full mt-2 rounded-lg border border-[#343451] py-2 text-xs font-bold text-purple-300 hover:border-[#9146FF] hover:text-white"
      >
        Edit video timeline
      </button>
      {open && (
        <div className="fixed inset-0 z-50 bg-black/85 p-4 sm:p-8 overflow-y-auto">
          <div className="max-w-5xl mx-auto rounded-3xl border border-[#343451] bg-[#101018] p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-xl font-black">Clip timeline</h2>
                <p className="text-xs text-gray-500">
                  Extend the story, restore AI cuts, or remove your own ranges.
                </p>
              </div>
              <button type="button" onClick={() => setOpen(false)}
                className="text-gray-400 hover:text-white">✕</button>
            </div>
            {!source ? (
              <div className="py-24 text-center text-gray-400">{message}</div>
            ) : (
              <>
                <div
                  className="mx-auto w-[min(420px,88vw)] outline-none"
                  tabIndex={0}
                  onKeyDown={onPlayerKeyDown}
                >
                  <div
                    className="group relative aspect-[9/16] overflow-hidden rounded-xl bg-black shadow-2xl"
                    onClick={togglePlayback}
                  >
                    <video
                      key={source.url}
                      ref={video}
                      src={source.url}
                      preload="auto"
                      playsInline
                      onLoadStart={() => setBuffering(true)}
                      onLoadedData={() => {
                        setBuffering(false);
                        setMediaError("");
                      }}
                      onCanPlay={() => setBuffering(false)}
                      onPlay={() => setPlaying(true)}
                      onPause={() => setPlaying(false)}
                      onWaiting={() => setBuffering(true)}
                      onPlaying={() => setBuffering(false)}
                      onStalled={() => setBuffering(true)}
                      onError={(event) => {
                        const code = event.currentTarget.error?.code;
                        setBuffering(false);
                        setMediaError(
                          code === 2
                            ? "The preview connection stalled."
                            : "The preview could not load."
                        );
                      }}
                      className="h-full w-full object-cover"
                    />
                    <div className="pointer-events-none absolute inset-0 grid place-items-center">
                      <div className={`grid h-16 w-16 place-items-center rounded-full bg-black/65 text-2xl text-white backdrop-blur transition ${
                        playing && !buffering ? "opacity-0 group-hover:opacity-100" : "opacity-100"
                      }`}>
                        {buffering ? "…" : playing ? "Ⅱ" : "▶"}
                      </div>
                    </div>
                    {buffering && (
                      <span className="pointer-events-none absolute inset-x-0 bottom-4 text-center text-[11px] font-bold text-white/80">
                        Loading instant preview…
                      </span>
                    )}
                    <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-black/70 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-white">
                      {playerMode === "edit" ? "Edit preview" : "Source inspect"}
                    </span>
                  </div>
                  {mediaError && (
                    <div className="mt-2 flex items-center justify-between gap-3 rounded-xl border border-red-500/35 bg-red-500/10 px-3 py-2">
                      <span className="text-xs text-red-200">{mediaError}</span>
                      <button
                        type="button"
                        onClick={retryPreview}
                        className="shrink-0 rounded-lg bg-white px-3 py-1.5 text-xs font-black text-black"
                      >
                        Retry preview
                      </button>
                    </div>
                  )}
                  <div className="mt-3 rounded-2xl border border-[#28283e] bg-[#0b0b11] p-3">
                    <div className="relative mb-1 h-2 overflow-hidden rounded-full bg-[#242436]">
                      <span
                        className="absolute inset-y-0 bg-[#9146FF]/70"
                        style={{
                          left: `${((start - source.lo) / (source.hi - source.lo)) * 100}%`,
                          width: `${((end - start) / (source.hi - source.lo)) * 100}%`,
                        }}
                      />
                      {cuts.map(([a, b], index) => (
                        <span
                          key={`track-${a}-${b}-${index}`}
                          className="absolute inset-y-0 bg-red-500/90"
                          style={{
                            left: `${((Math.max(source.lo, a) - source.lo) / (source.hi - source.lo)) * 100}%`,
                            width: `${((Math.min(source.hi, b) - Math.max(source.lo, a)) / (source.hi - source.lo)) * 100}%`,
                          }}
                        />
                      ))}
                      <span
                        className="absolute -top-1 h-4 w-0.5 bg-white"
                        style={{
                          left: `${((playhead - source.lo) / (source.hi - source.lo)) * 100}%`,
                        }}
                      />
                    </div>
                    <input
                      aria-label="Video playhead"
                      type="range"
                      min={source.lo}
                      max={source.hi}
                      step=".05"
                      value={Math.max(source.lo, Math.min(source.hi, playhead))}
                      onChange={(event) => seekTo(event.target.value)}
                      className="w-full accent-[#9146FF]"
                    />
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="min-w-[62px] font-mono text-[11px] text-gray-400">
                        {formatTime(playhead - source.lo)}
                      </span>
                      <div className="flex items-center gap-2">
                        <button type="button" onClick={() => seekTo(playhead - 5)}
                          className="rounded-lg bg-[#23233a] px-3 py-2 text-xs font-black">
                          −5s
                        </button>
                        <button type="button" onClick={togglePlayback}
                          className="grid h-11 w-11 place-items-center rounded-full bg-white text-base font-black text-black">
                          {playing ? "Ⅱ" : "▶"}
                        </button>
                        <button type="button" onClick={() => seekTo(playhead + 5)}
                          className="rounded-lg bg-[#23233a] px-3 py-2 text-xs font-black">
                          +5s
                        </button>
                      </div>
                      <span className="min-w-[62px] text-right font-mono text-[11px] text-gray-400">
                        {formatTime(source.hi - source.lo)}
                      </span>
                    </div>
                    <button type="button" onClick={playEdit}
                      className="mt-3 w-full rounded-xl border border-[#9146FF]/60 bg-[#9146FF]/15 py-2.5 text-xs font-black text-purple-200 hover:bg-[#9146FF]/25">
                      Preview edit from selected start
                    </button>
                    <p className="mt-2 text-center text-[10px] text-gray-600">
                      Space: play/pause · ←/→: inspect source ±5s
                    </p>
                  </div>
                  <p className="mt-2 text-center text-[11px] text-gray-500">
                    Instant draft · 360×640 vertical · final exports at 1080×1920
                  </p>
                </div>
                <div className="mt-5">
                  <EditableTimeline
                    source={source}
                    start={start}
                    end={end}
                    cuts={cuts}
                    waveform={source.waveform}
                    playhead={playhead}
                    onSeek={seekTo}
                    onStartChange={(value) => setStart(round(value))}
                    onEndChange={(value) => setEnd(round(value))}
                    onDeleteRange={(range) => {
                      setCuts([...cuts, range]);
                      setMessage("Range removed from preview. Restore it below if needed.");
                    }}
                    onCutsChange={setCuts}
                    onRestoreCut={(index) => {
                      setCuts(cuts.filter((_, current) => current !== index));
                      setMessage("");
                    }}
                  />
                  <div className="mt-4 flex items-center justify-between gap-4">
                    <span className="text-xs text-gray-400">{message}</span>
                    <button type="button" onClick={renderRevision}
                      disabled={exporting}
                      className="shrink-0 rounded-xl bg-[#9146FF] px-5 py-2.5 text-sm font-black hover:bg-[#7a2ff0] disabled:cursor-wait disabled:opacity-60">
                      {exporting ? "Exporting…" : "Export final 1080×1920"}
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
