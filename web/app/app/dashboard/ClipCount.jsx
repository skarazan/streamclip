"use client";

import { useState } from "react";

export default function ClipCount({ initial }) {
  const [value, setValue] = useState(initial ?? 3);
  const [saving, setSaving] = useState(false);

  const update = async (n) => {
    const prev = value;
    setValue(n);
    setSaving(true);
    const r = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clips_per_stream: n }),
    });
    if (!r.ok) setValue(prev);
    setSaving(false);
  };

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-gray-400">Clips per stream</span>
      <div className="flex rounded-lg border border-[#2e2e4a] bg-[#15151f] overflow-hidden">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} onClick={() => update(n)} disabled={saving}
            className={`px-3 py-1.5 font-bold ${
              n === value ? "bg-[#9146FF] text-white" : "text-gray-400 hover:text-white"
            }`}>
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}
