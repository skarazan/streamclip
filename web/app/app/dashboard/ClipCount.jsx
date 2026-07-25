"use client";

import { useEffect, useRef, useState } from "react";

export const CLIP_COUNT_STORAGE_KEY = "streamclip.clips_per_stream";

export default function ClipCount({ initial }) {
  const [value, setValue] = useState(initial ?? 3);
  const [status, setStatus] = useState("");
  const desired = useRef(initial ?? 3);
  const saved = useRef(initial ?? 3);
  const draining = useRef(false);

  useEffect(() => {
    localStorage.setItem(CLIP_COUNT_STORAGE_KEY, String(initial ?? 3));
  }, [initial]);

  const persistLatest = async () => {
    if (draining.current) return;
    draining.current = true;
    setStatus("Saving…");
    while (desired.current !== saved.current) {
      const target = desired.current;
      const r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clips_per_stream: target }),
      }).catch(() => null);
      if (!r?.ok) {
        desired.current = saved.current;
        setValue(saved.current);
        localStorage.setItem(CLIP_COUNT_STORAGE_KEY, String(saved.current));
        setStatus("Couldn’t save");
        draining.current = false;
        return;
      }
      saved.current = target;
    }
    setStatus("Saved");
    draining.current = false;
  };

  const update = (n) => {
    desired.current = n;
    setValue(n);
    localStorage.setItem(CLIP_COUNT_STORAGE_KEY, String(n));
    persistLatest();
  };

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-gray-400">
        Clips per stream
        {status && (
          <span className={`block text-[9px] text-right ${
            status === "Couldn’t save" ? "text-red-400" : "text-gray-600"
          }`}>
            {status}
          </span>
        )}
      </span>
      <div className="flex rounded-lg border border-[#2e2e4a] bg-[#15151f] overflow-hidden">
        {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
          <button key={n} type="button" onClick={() => update(n)}
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
