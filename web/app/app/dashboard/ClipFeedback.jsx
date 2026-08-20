"use client";

import { useState } from "react";

const REASONS = [
  ["weak_moment", "Weak moment"],
  ["missing_context", "Missing context"],
  ["cause_not_visible", "Cause not visible"],
  ["slow_or_redundant", "Slow / repetitive"],
  ["starts_late", "Starts too late"],
  ["ends_early", "Ends too early"],
  ["bad_title", "Bad title"],
  ["bad_framing", "Bad framing"],
  ["technical", "Technical issue"],
  ["other", "Other"],
];

export default function ClipFeedback({ clipId, initial, initialReason }) {
  const [value, setValue] = useState(initial);
  const [reason, setReason] = useState(initialReason || "");
  const [choosingReason, setChoosingReason] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const save = async (feedback, feedbackReason) => {
    if (busy) return;
    const previous = value;
    const previousReason = reason;
    setValue(feedback);
    setReason(feedbackReason);
    setChoosingReason(false);
    setError("");
    setBusy(true);
    const response = await fetch(`/api/clips/${clipId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback, feedback_reason: feedbackReason }),
    }).catch(() => null);
    if (!response?.ok) {
      setValue(previous);
      setReason(previousReason);
      setError("Couldn’t save — try again");
    } else {
      window.plausible?.("Clip Rated", {
        props: { feedback, reason: feedbackReason },
      });
    }
    setBusy(false);
  };

  const vote = (feedback) => {
    if (busy) return;
    if (feedback === 1) {
      save(1, "good_as_is");
    } else {
      setChoosingReason(true);
    }
  };

  return (
    <div className="mt-3 rounded-lg border border-[#282840] px-3 py-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">Would you post this?</span>
        <div className="flex gap-2">
          <button type="button" onClick={() => vote(1)} aria-label="Keep clip"
            disabled={busy}
            className={`rounded-md px-2 py-1 text-sm disabled:opacity-50 ${value === 1 ? "bg-green-900/50 ring-1 ring-green-700" : "bg-[#202033]"}`}>👍</button>
          <button type="button" onClick={() => vote(-1)} aria-label="Discard clip"
            disabled={busy}
            className={`rounded-md px-2 py-1 text-sm disabled:opacity-50 ${value === -1 ? "bg-red-900/50 ring-1 ring-red-700" : "bg-[#202033]"}`}>👎</button>
        </div>
      </div>
      {(choosingReason || value === -1) && (
        <div className="mt-2">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-gray-500">
            What failed? One tap teaches the next selector.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {REASONS.map(([id, label]) => (
              <button key={id} type="button" onClick={() => save(-1, id)}
                disabled={busy}
                className={`rounded-full border px-2.5 py-1 text-[10px] font-bold disabled:opacity-50 ${
                  reason === id
                    ? "border-red-700 bg-red-950/50 text-red-200"
                    : "border-[#343451] bg-[#171724] text-gray-400 hover:border-red-800 hover:text-white"
                }`}>
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-[10px] text-red-400">{error}</p>}
    </div>
  );
}
