"use client";

import { useState } from "react";
import { STYLE_PRESETS } from "../../lib/stylePresets";

function Preview({ p }) {
  const base = {
    fontFamily: p.fontFamily,
    fontWeight: p.fontWeight,
    textTransform: p.textTransform,
    textShadow: p.textShadow,
    background: p.background,
    padding: p.padding,
    borderRadius: p.borderRadius,
    lineHeight: 1.15,
  };
  return (
    <div className="h-20 rounded-xl bg-[#0c0c13] border border-[#1c1c2e] flex items-center justify-center overflow-hidden">
      <span style={{ ...base, color: p.color }} className="text-lg">
        that was{" "}
        <span style={{ color: p.highlight, transform: "scale(1.1)", display: "inline-block" }}>
          insane
        </span>
      </span>
    </div>
  );
}

export default function StylePicker({ initial }) {
  const [selected, setSelected] = useState(initial || "classic");
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");

  const pick = async (key) => {
    if (key === selected || saving) return;
    setSaving(key);
    setError("");
    const prev = selected;
    setSelected(key);
    const r = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ style_preset: key }),
    }).catch(() => null);
    if (!r?.ok) {
      setSelected(prev);
      setError("couldn't save — try again");
    }
    setSaving("");
  };

  return (
    <div className="mb-10">
      <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wide mb-3">
        Caption style
      </h2>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Object.entries(STYLE_PRESETS).map(([key, p]) => (
          <button
            key={key}
            onClick={() => pick(key)}
            className={`text-left rounded-2xl p-3 border transition
              ${selected === key
                ? "border-[#9146FF] bg-[#17131f]"
                : "border-[#23233a] bg-[#12121a] hover:border-[#3a3a5c]"}`}
          >
            <Preview p={p.preview} />
            <div className="mt-2 flex items-center justify-between">
              <span className="font-bold text-sm">{p.label}</span>
              {selected === key && (
                <span className="text-[10px] font-black text-purple-300">
                  {saving === key ? "SAVING…" : "ACTIVE"}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 mt-1 leading-snug">{p.desc}</p>
          </button>
        ))}
      </div>
      {error && <p className="text-sm text-red-400 mt-2">{error}</p>}
      <p className="text-xs text-gray-500 mt-2">
        Applies to your next clip job.
      </p>
    </div>
  );
}
