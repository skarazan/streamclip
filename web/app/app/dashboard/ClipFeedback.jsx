"use client";

import { useState } from "react";

export default function ClipFeedback({ clipId, initial }) {
  const [value, setValue] = useState(initial);
  const [busy, setBusy] = useState(false);
  const vote = async (feedback) => {
    if (busy || value === feedback) return;
    const previous = value;
    setValue(feedback);
    setBusy(true);
    const response = await fetch(`/api/clips/${clipId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback }),
    }).catch(() => null);
    if (!response?.ok) setValue(previous);
    else window.plausible?.("Clip Rated", { props: { feedback } });
    setBusy(false);
  };
  return (
    <div className="mt-3 flex items-center justify-between rounded-lg border border-[#282840] px-3 py-2">
      <span className="text-xs text-gray-500">Would you post this?</span>
      <div className="flex gap-2">
        <button type="button" onClick={() => vote(1)} aria-label="Good clip"
          className={`rounded-md px-2 py-1 text-sm ${value === 1 ? "bg-green-900/50" : "bg-[#202033]"}`}>👍</button>
        <button type="button" onClick={() => vote(-1)} aria-label="Bad clip"
          className={`rounded-md px-2 py-1 text-sm ${value === -1 ? "bg-red-900/50" : "bg-[#202033]"}`}>👎</button>
      </div>
    </div>
  );
}
