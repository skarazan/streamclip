"use client";

import { useState } from "react";

export default function ClipEditor({ clipId, initialTitle, initialHook }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(initialTitle);
  const [hook, setHook] = useState(initialHook);
  const [draftTitle, setDraftTitle] = useState(initialTitle);
  const [draftHook, setDraftHook] = useState(initialHook);
  const [message, setMessage] = useState("");

  const save = async () => {
    setMessage("Saving…");
    const r = await fetch(`/api/clips/${clipId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: draftTitle, hook: draftHook }),
    }).catch(() => null);
    if (!r?.ok) {
      const data = await r?.json().catch(() => ({}));
      setMessage(data?.error || "Couldn’t save");
      return;
    }
    setTitle(draftTitle.trim());
    setHook(draftHook.trim());
    setMessage("");
    setEditing(false);
  };

  if (!editing) {
    return (
      <div className="min-w-0 flex-1">
        <p className="font-bold leading-snug">{title}</p>
        {hook && <p className="text-xs text-gray-400 mt-1">{hook}</p>}
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-[10px] font-bold text-purple-300 hover:text-white mt-2"
        >
          Edit title + hook
        </button>
      </div>
    );
  }

  return (
    <div className="min-w-0 flex-1 space-y-2">
      <input
        value={draftTitle}
        onChange={(e) => setDraftTitle(e.target.value)}
        maxLength={100}
        aria-label="Clip title"
        className="w-full rounded-lg bg-[#0c0c13] border border-[#343451] px-2.5 py-2 text-sm font-bold focus:outline-none focus:border-[#9146FF]"
      />
      <input
        value={draftHook}
        onChange={(e) => setDraftHook(e.target.value)}
        maxLength={80}
        aria-label="On-screen hook"
        className="w-full rounded-lg bg-[#0c0c13] border border-[#343451] px-2.5 py-2 text-xs focus:outline-none focus:border-[#9146FF]"
      />
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={save}
          disabled={draftTitle.trim().length < 4 || message === "Saving…"}
          className="rounded-md bg-[#9146FF] px-2.5 py-1 text-[10px] font-black disabled:opacity-50"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => {
            setDraftTitle(title);
            setDraftHook(hook);
            setMessage("");
            setEditing(false);
          }}
          className="text-[10px] text-gray-400 hover:text-white"
        >
          Cancel
        </button>
        {message && (
          <span className={message === "Saving…" ? "text-gray-500 text-[10px]" : "text-red-400 text-[10px]"}>
            {message}
          </span>
        )}
      </div>
    </div>
  );
}
