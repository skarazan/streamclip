"use client";

import { useState } from "react";

export default function PortalButton() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const open = async () => {
    setBusy(true);
    setError("");
    const response = await fetch("/api/billing/portal", { method: "POST" });
    const data = await response.json();
    if (response.ok) window.location.assign(data.url);
    else {
      setError(data.error || "Billing portal unavailable.");
      setBusy(false);
    }
  };
  return (
    <div>
      <button type="button" onClick={open} disabled={busy}
        className="rounded-xl border border-[#343451] px-5 py-3 font-black disabled:opacity-60">
        {busy ? "Opening…" : "Manage subscription"}
      </button>
      {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
    </div>
  );
}
