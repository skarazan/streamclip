"use client";

import { useEffect, useState } from "react";

export default function WorkerStatusBanner() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        const data = await response.json();
        if (alive) setHealth(data);
      } catch {
        if (alive) setHealth({ delayed: true, state: "unknown" });
      }
    };
    check();
    const timer = window.setInterval(check, 60_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  if (!health?.delayed) return null;
  return (
    <div className="mb-6 rounded-2xl border border-amber-700/60 bg-amber-950/25 px-5 py-4">
      <p className="font-bold text-amber-200">Processing is delayed</p>
      <p className="mt-1 text-sm text-amber-100/70">
        Your dashboard and existing clips are safe. New jobs stay queued until
        the worker reconnects; there is no need to submit them again.
      </p>
    </div>
  );
}
