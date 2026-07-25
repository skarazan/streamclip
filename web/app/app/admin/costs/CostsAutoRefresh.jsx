"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const POLL_MS = 3000;

/**
 * Founder-only page, so it re-renders on a plain interval instead of the
 * dashboard's digest check: there is exactly one viewer and a running job's
 * cost has to visibly grow. Paused while the tab is hidden so an open tab
 * overnight doesn't hammer Supabase for nobody.
 */
export default function CostsAutoRefresh() {
  const router = useRouter();

  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === "visible") router.refresh();
    };
    const timer = window.setInterval(tick, POLL_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [router]);

  return null;
}
