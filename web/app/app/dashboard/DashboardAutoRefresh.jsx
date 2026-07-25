"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

const POLL_MS = 3000;

export default function DashboardAutoRefresh() {
  const router = useRouter();
  const signature = useRef(null);
  const refreshing = useRef(false);
  const checking = useRef(false);

  useEffect(() => {
    let alive = true;

    const check = async () => {
      if (!alive || document.visibilityState === "hidden" || checking.current) {
        return;
      }
      checking.current = true;
      try {
        const response = await fetch("/api/dashboard-state", {
          cache: "no-store",
        });
        if (!response.ok) return;
        const data = await response.json();
        if (signature.current == null) {
          signature.current = data.signature;
          return;
        }
        if (signature.current !== data.signature && !refreshing.current) {
          signature.current = data.signature;
          refreshing.current = true;
          router.refresh();
          // Coalesce a burst of progress + clip insert + job completion into
          // one server refresh while ActiveJobs continues updating locally.
          window.setTimeout(() => { refreshing.current = false; }, 750);
        }
      } catch {
        // A transient refresh check must never disrupt editing or playback.
      } finally {
        checking.current = false;
      }
    };

    check();
    const timer = window.setInterval(check, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") check();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [router]);

  return null;
}
