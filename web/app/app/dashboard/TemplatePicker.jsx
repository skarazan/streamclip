"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { OPENING_EFFECTS, TITLE_STRATEGIES } from "../../lib/contentPresets";

function Choice({ active, children, onClick, disabled }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`text-left rounded-2xl p-4 border transition disabled:opacity-60
        ${active
          ? "border-[#9146FF] bg-[#17131f] shadow-[0_0_0_1px_rgba(145,70,255,.16)]"
          : "border-[#23233a] bg-[#12121a] hover:border-[#3a3a5c]"}`}
    >
      {children}
    </button>
  );
}

export default function TemplatePicker({ initial = {} }) {
  const router = useRouter();
  const [titleStrategy, setTitleStrategy] = useState(
    initial.title_strategy || "curiosity"
  );
  const [openingEffect, setOpeningEffect] = useState(
    initial.opening_effect || "punch_zoom"
  );
  const [saving, setSaving] = useState("");
  const [message, setMessage] = useState("");

  const save = async (field, value, previous, rollback) => {
    setSaving(field);
    setMessage("");
    const r = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [field]: value }),
    }).catch(() => null);
    if (!r?.ok) {
      rollback(previous);
      const data = await r?.json().catch(() => ({}));
      setMessage(data?.error || "Couldn’t save this template.");
    } else {
      setMessage("Saved for the next run.");
      router.refresh();
    }
    setSaving("");
  };

  const chooseTitle = (key) => {
    if (saving || key === titleStrategy) return;
    const previous = titleStrategy;
    setTitleStrategy(key);
    save("title_strategy", key, previous, setTitleStrategy);
  };

  const chooseOpening = (key) => {
    if (saving || key === openingEffect) return;
    const previous = openingEffect;
    setOpeningEffect(key);
    save("opening_effect", key, previous, setOpeningEffect);
  };

  return (
    <section className="mb-10 rounded-3xl border border-[#23233a] bg-[#0f0f17] p-5 sm:p-6">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 mb-5">
        <div>
          <p className="text-xs font-black tracking-[0.18em] text-purple-300 uppercase">
            Retention template
          </p>
          <h2 className="text-xl font-black mt-1">Package the first impression</h2>
        </div>
        <p className="text-xs text-gray-500 max-w-md">
          Templates change presentation only. Story and evidence gates stay automatic.
        </p>
      </div>

      <div className="mb-7">
        <h3 className="text-sm font-bold text-gray-300 mb-3">Title strategy</h3>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {Object.entries(TITLE_STRATEGIES).map(([key, item]) => (
            <Choice
              key={key}
              active={titleStrategy === key}
              disabled={Boolean(saving)}
              onClick={() => chooseTitle(key)}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold">{item.label}</span>
                {titleStrategy === key && (
                  <span className="text-[10px] font-black text-purple-300">ACTIVE</span>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-1.5 leading-snug">{item.desc}</p>
              <p className="text-xs text-gray-300 mt-3 italic leading-snug">
                {item.example}
              </p>
            </Choice>
          ))}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-bold text-gray-300 mb-3">Opening pattern</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Object.entries(OPENING_EFFECTS).map(([key, item]) => (
            <Choice
              key={key}
              active={openingEffect === key}
              disabled={Boolean(saving)}
              onClick={() => chooseOpening(key)}
            >
              <div className="h-14 rounded-xl bg-[#09090e] border border-[#1c1c2e] grid place-items-center overflow-hidden">
                <span
                  className={`text-2xl text-purple-300 ${
                    key === "punch_zoom" || key === "impact" ? "scale-125" : ""
                  }`}
                >
                  {item.glyph}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2 mt-3">
                <span className="font-bold text-sm">{item.label}</span>
                {openingEffect === key && (
                  <span className="text-[10px] font-black text-purple-300">ACTIVE</span>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-1 leading-snug">{item.desc}</p>
            </Choice>
          ))}
        </div>
      </div>

      <div className="h-5 mt-3 text-xs">
        {saving ? (
          <span className="text-gray-400">Saving…</span>
        ) : message ? (
          <span className={message.startsWith("Saved") ? "text-green-400" : "text-red-400"}>
            {message}
          </span>
        ) : null}
      </div>
    </section>
  );
}
