"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const round = (value) => Math.round(value * 10) / 10;

function stamp(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const rest = safe - minutes * 60;
  return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
}

export default function EditableTimeline({
  source,
  start,
  end,
  cuts,
  waveform,
  playhead,
  onSeek,
  onStartChange,
  onEndChange,
  onDeleteRange,
  onCutsChange,
  onRestoreCut,
}) {
  const track = useRef(null);
  const scroller = useRef(null);
  const dragging = useRef(null);
  const [selection, setSelection] = useState(null);
  const [zoom, setZoom] = useState(1);
  const duration = Math.max(.1, source.hi - source.lo);
  const selectedDuration = Math.max(0, end - start);
  const removedDuration = cuts.reduce((total, [a, b]) => (
    total + Math.max(0, Math.min(end, b) - Math.max(start, a))
  ), 0);

  const percent = (time) =>
    clamp(((time - source.lo) / duration) * 100, 0, 100);

  const waveformPath = useMemo(() => {
    if (!waveform?.length) return "";
    const width = 1000;
    const middle = 112;
    const amplitude = 31;
    const top = waveform.map((peak, index) => {
      const x = (index / Math.max(1, waveform.length - 1)) * width;
      return `${x.toFixed(1)},${(middle - peak * amplitude).toFixed(1)}`;
    });
    const bottom = [...waveform].reverse().map((peak, reverseIndex) => {
      const index = waveform.length - 1 - reverseIndex;
      const x = (index / Math.max(1, waveform.length - 1)) * width;
      return `${x.toFixed(1)},${(middle + peak * amplitude).toFixed(1)}`;
    });
    return `M ${top.join(" L ")} L ${bottom.join(" L ")} Z`;
  }, [waveform]);

  const timeAt = (clientX) => {
    const rect = track.current?.getBoundingClientRect();
    if (!rect) return source.lo;
    return round(source.lo + clamp((clientX - rect.left) / rect.width, 0, 1) * duration);
  };

  const move = (kind, clientX) => {
    const scrollBox = scroller.current;
    if (scrollBox) {
      const bounds = scrollBox.getBoundingClientRect();
      if (clientX < bounds.left + 36) scrollBox.scrollLeft -= 18;
      if (clientX > bounds.right - 36) scrollBox.scrollLeft += 18;
    }
    const at = timeAt(clientX);
    if (kind === "playhead") {
      onSeek(at);
    } else if (kind === "start") {
      onStartChange(clamp(at, source.lo, end - .5));
    } else if (kind === "end") {
      onEndChange(clamp(at, start + .5, source.hi));
    } else if (kind === "selection-start" && selection) {
      setSelection([clamp(at, start, selection[1] - .2), selection[1]]);
    } else if (kind === "selection-end" && selection) {
      setSelection([selection[0], clamp(at, selection[0] + .2, end)]);
    } else if (kind.startsWith("cut-start:")) {
      const index = Number(kind.split(":")[1]);
      onCutsChange(cuts.map((cut, current) => (
        current === index
          ? [clamp(at, start, cut[1] - .2), cut[1]]
          : cut
      )));
    } else if (kind.startsWith("cut-end:")) {
      const index = Number(kind.split(":")[1]);
      onCutsChange(cuts.map((cut, current) => (
        current === index
          ? [cut[0], clamp(at, cut[0] + .2, end)]
          : cut
      )));
    }
  };

  const beginDrag = (kind, event) => {
    event.preventDefault();
    event.stopPropagation();
    dragging.current = kind;
    move(kind, event.clientX);
  };

  useEffect(() => {
    const onMove = (event) => {
      if (dragging.current) move(dragging.current, event.clientX);
    };
    const onUp = () => {
      dragging.current = null;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  });

  useEffect(() => {
    const box = scroller.current;
    if (!box) return;
    const center = percent(playhead) / 100 * box.scrollWidth;
    box.scrollLeft = Math.max(0, center - box.clientWidth / 2);
    // Zoom is the trigger; following the playhead during playback would make
    // the timeline constantly auto-scroll under the user's pointer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom]);

  const beginSelection = () => {
    const center = clamp(playhead, start, end);
    let a = clamp(center - 1.5, start, end - .2);
    let b = clamp(center + 1.5, a + .2, end);
    if (b - a < .2) a = Math.max(start, b - .2);
    setSelection([round(a), round(b)]);
  };

  const deleteSelection = () => {
    if (!selection || selection[1] - selection[0] < .2) return;
    onDeleteRange(selection);
    setSelection(null);
  };

  const ticks = Array.from(
    { length: 4 * zoom + 1 },
    (_, index) => index / (4 * zoom)
  );

  return (
    <section className="rounded-2xl border border-[#28283e] bg-[#0b0b11] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-black text-white">Timeline</h3>
          <p className="text-[11px] text-gray-500">
            Drag the purple handles to trim. Drag the white line to scrub.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-3 text-[10px] font-bold uppercase tracking-wide">
            <span className="flex items-center gap-1.5 text-purple-300">
              <i className="h-2 w-2 rounded-sm bg-[#9146FF]" /> Keep
            </span>
            <span className="flex items-center gap-1.5 text-red-300">
              <i className="h-2 w-2 rounded-sm bg-red-500" /> Removed
            </span>
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-[#343451] bg-[#151520] p-1">
            {[1, 2, 4, 8].map((level) => (
              <button
                key={level}
                type="button"
                aria-label={level === 1 ? "Fit timeline" : `Zoom timeline ${level} times`}
                onClick={() => setZoom(level)}
                className={`min-w-11 rounded-md px-2 py-1.5 text-[10px] font-black ${
                  zoom === level
                    ? "bg-[#9146FF] text-white"
                    : "text-gray-400 hover:bg-[#29293d] hover:text-white"
                }`}
              >
                {level === 1 ? "Fit" : `${level}×`}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div
        ref={scroller}
        className="overflow-x-auto pb-2 [scrollbar-color:#4b4b68_#171721]"
        onWheel={(event) => {
          if (!event.ctrlKey && !event.metaKey) return;
          event.preventDefault();
          setZoom(event.deltaY < 0
            ? Math.min(8, zoom * 2)
            : Math.max(1, zoom / 2));
        }}
      >
        <div
          className="min-w-full"
          style={{ width: `${zoom * 100}%` }}
        >
          <div className="relative mb-1 h-5 select-none text-[9px] text-gray-600">
            {ticks.map((tick) => (
              <span
                key={tick}
                className="absolute -translate-x-1/2"
                style={{ left: `${tick * 100}%` }}
              >
                {stamp(duration * tick)}
              </span>
            ))}
          </div>

          <div
            ref={track}
            data-testid="editable-timeline"
            className="relative h-36 cursor-ew-resize touch-none select-none overflow-hidden rounded-xl border border-[#343451] bg-[#181824]"
            onPointerDown={(event) => beginDrag("playhead", event)}
          >
            <div
              className="absolute inset-0 opacity-25"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(90deg, transparent 0, transparent 31px, #8b8ba7 32px), linear-gradient(180deg, #39394d 0%, #171721 100%)",
              }}
            />
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[62px] border-t border-white/10 bg-black/20">
              <span className="absolute left-2 top-1 text-[8px] font-black uppercase tracking-[.2em] text-gray-600">
                Audio
              </span>
              {waveformPath ? (
                <svg
                  viewBox="0 70 1000 75"
                  preserveAspectRatio="none"
                  className="absolute inset-0 h-full w-full"
                >
                  <path d={waveformPath} fill="#d8ccff" opacity=".72" />
                  <line x1="0" y1="112" x2="1000" y2="112" stroke="#ffffff" strokeOpacity=".12" />
                </svg>
              ) : (
                <span className="absolute inset-0 grid place-items-center text-[9px] text-gray-600">
                  Preparing waveform…
                </span>
              )}
            </div>
            <div
              className="absolute inset-y-0 border-y-2 border-[#9146FF] bg-[#9146FF]/15"
              style={{
                left: `${percent(start)}%`,
                width: `${percent(end) - percent(start)}%`,
              }}
            />
            <div
              className="pointer-events-none absolute inset-y-0 left-0 bg-black/70"
              style={{ width: `${percent(start)}%` }}
            />
            <div
              className="pointer-events-none absolute inset-y-0 right-0 bg-black/70"
              style={{ width: `${100 - percent(end)}%` }}
            />

            {cuts.map(([a, b], index) => {
              const left = percent(Math.max(start, a));
              const right = percent(Math.min(end, b));
              if (right <= left) return null;
              return (
                <div
                  key={`cut-${index}`}
                  className="absolute inset-y-0 z-10 border-x border-red-200/70 bg-red-600/60"
                  style={{ left: `${left}%`, width: `${right - left}%` }}
                >
                  <span className="pointer-events-none absolute left-1/2 top-2 -translate-x-1/2 whitespace-nowrap rounded bg-black/75 px-1.5 py-0.5 font-mono text-[9px] text-red-100">
                    {stamp(a - source.lo)}–{stamp(b - source.lo)}
                  </span>
                  <button
                    type="button"
                    aria-label={`Adjust removed range ${index + 1} start`}
                    onPointerDown={(event) => beginDrag(`cut-start:${index}`, event)}
                    className="group absolute -left-4 inset-y-0 z-20 w-8 cursor-ew-resize bg-transparent"
                  >
                    <span className="absolute inset-y-0 left-1/2 w-[3px] -translate-x-1/2 bg-red-100 shadow-[0_0_0_1px_#ef4444]" />
                    <span className="absolute left-1/2 top-1/2 h-8 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-red-100 bg-red-500 opacity-75 group-hover:opacity-100" />
                  </button>
                  <button
                    type="button"
                    aria-label={`Adjust removed range ${index + 1} end`}
                    onPointerDown={(event) => beginDrag(`cut-end:${index}`, event)}
                    className="group absolute -right-4 inset-y-0 z-20 w-8 cursor-ew-resize bg-transparent"
                  >
                    <span className="absolute inset-y-0 left-1/2 w-[3px] -translate-x-1/2 bg-red-100 shadow-[0_0_0_1px_#ef4444]" />
                    <span className="absolute left-1/2 top-1/2 h-8 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-red-100 bg-red-500 opacity-75 group-hover:opacity-100" />
                  </button>
                </div>
              );
            })}

            {selection && (
              <div
                className="absolute inset-y-2 z-20 border-2 border-red-300 bg-red-500/30"
                style={{
                  left: `${percent(selection[0])}%`,
                  width: `${percent(selection[1]) - percent(selection[0])}%`,
                }}
              >
                <span className="pointer-events-none absolute left-1/2 top-2 -translate-x-1/2 whitespace-nowrap rounded bg-black/80 px-1.5 py-0.5 font-mono text-[9px] text-white">
                  {stamp(selection[0] - source.lo)}–{stamp(selection[1] - source.lo)}
                </span>
                <button
                  type="button"
                  aria-label="Drag removal start"
                  onPointerDown={(event) => beginDrag("selection-start", event)}
                  className="absolute -left-4 inset-y-0 w-8 cursor-ew-resize bg-transparent"
                >
                  <span className="absolute inset-y-0 left-1/2 w-[3px] -translate-x-1/2 bg-red-100" />
                </button>
                <button
                  type="button"
                  aria-label="Drag removal end"
                  onPointerDown={(event) => beginDrag("selection-end", event)}
                  className="absolute -right-4 inset-y-0 w-8 cursor-ew-resize bg-transparent"
                >
                  <span className="absolute inset-y-0 left-1/2 w-[3px] -translate-x-1/2 bg-red-100" />
                </button>
              </div>
            )}

            <button
              type="button"
              aria-label="Drag clip start"
              onPointerDown={(event) => beginDrag("start", event)}
              className="group absolute inset-y-0 z-30 w-10 -translate-x-1/2 cursor-ew-resize bg-transparent"
              style={{ left: `${percent(start)}%` }}
            >
              <span className="absolute left-1/2 top-2 -translate-x-1/2 whitespace-nowrap rounded bg-[#2b1747] px-1.5 py-0.5 font-mono text-[9px] text-white">
                {stamp(start - source.lo)}
              </span>
              <span className="absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 bg-[#c9a7ff] shadow-[0_0_0_1px_#7c3aed]" />
              <span className="absolute left-1/2 top-1/2 h-10 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#9146FF] opacity-80 group-hover:opacity-100" />
            </button>
            <button
              type="button"
              aria-label="Drag clip end"
              onPointerDown={(event) => beginDrag("end", event)}
              className="group absolute inset-y-0 z-30 w-10 -translate-x-1/2 cursor-ew-resize bg-transparent"
              style={{ left: `${percent(end)}%` }}
            >
              <span className="absolute right-1/2 top-2 translate-x-1/2 whitespace-nowrap rounded bg-[#2b1747] px-1.5 py-0.5 font-mono text-[9px] text-white">
                {stamp(end - source.lo)}
              </span>
              <span className="absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 bg-[#c9a7ff] shadow-[0_0_0_1px_#7c3aed]" />
              <span className="absolute left-1/2 top-1/2 h-10 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#9146FF] opacity-80 group-hover:opacity-100" />
            </button>

            <button
              type="button"
              aria-label="Drag playhead"
              onPointerDown={(event) => beginDrag("playhead", event)}
              className="absolute inset-y-0 z-40 w-7 -translate-x-1/2 cursor-ew-resize"
              style={{ left: `${percent(playhead)}%` }}
            >
              <span className="absolute left-1/2 top-0 h-4 w-4 -translate-x-1/2 rotate-45 rounded-sm bg-white shadow" />
              <span className="absolute bottom-0 left-1/2 top-1 w-0.5 -translate-x-1/2 bg-white shadow" />
            </button>
          </div>
        </div>
      </div>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[10px] text-gray-600">
        <span>
          {zoom === 1
            ? "Fit shows the complete source"
            : `${zoom}× shows about ${stamp(duration / zoom)} at once · scroll horizontally`}
        </span>
        <span>Ctrl/Cmd + wheel or trackpad pinch to zoom</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => onStartChange(Math.max(source.lo, round(start - 15)))}
          className="rounded-lg bg-[#23233a] px-3 py-2 text-xs font-bold hover:bg-[#30304a]"
        >
          Add 15s before
        </button>
        <button
          type="button"
          onClick={() => onEndChange(Math.min(source.hi, round(end + 15)))}
          className="rounded-lg bg-[#23233a] px-3 py-2 text-xs font-bold hover:bg-[#30304a]"
        >
          Add 15s after
        </button>
        <button
          type="button"
          onClick={() => onStartChange(clamp(playhead, source.lo, end - .5))}
          className="rounded-lg border border-[#343451] px-3 py-2 text-xs font-bold hover:border-purple-400"
        >
          Start here
        </button>
        <button
          type="button"
          onClick={() => onEndChange(clamp(playhead, start + .5, source.hi))}
          className="rounded-lg border border-[#343451] px-3 py-2 text-xs font-bold hover:border-purple-400"
        >
          End here
        </button>
        {!selection ? (
          <button
            type="button"
            onClick={beginSelection}
            className="ml-auto rounded-lg border border-red-900/80 bg-red-950/30 px-3 py-2 text-xs font-bold text-red-300 hover:bg-red-950/60"
          >
            Select range to remove
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setSelection(null)}
              className="ml-auto rounded-lg px-3 py-2 text-xs font-bold text-gray-400"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={deleteSelection}
              className="rounded-lg bg-red-600 px-3 py-2 text-xs font-black text-white hover:bg-red-500"
            >
              Delete selected range
            </button>
          </>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[#222235] pt-3">
        <span className="text-xs text-gray-400">
          Final length: <strong className="text-white">
            {stamp(selectedDuration - removedDuration)}
          </strong>
        </span>
        <div className="flex flex-wrap gap-2">
          {cuts.map(([a, b], index) => (
            <button
              key={`restore-${a}-${b}-${index}`}
              type="button"
              onClick={() => onRestoreCut(index)}
              className="rounded-full border border-red-900/60 px-2.5 py-1 text-[10px] font-bold text-red-300 hover:border-red-400"
            >
              Restore {stamp(a - source.lo)}–{stamp(b - source.lo)}
            </button>
          ))}
          {cuts.length === 0 && (
            <span className="text-[11px] text-gray-600">No removed sections</span>
          )}
        </div>
      </div>
    </section>
  );
}
