"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function CheckoutReconciler({ sessionId }) {
  const router = useRouter();
  const [message, setMessage] = useState("Confirming payment with Stripe…");
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    fetch("/api/billing/reconcile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Could not confirm payment.");
        if (!active) return;
        setMessage("Payment confirmed. Your plan and credits are ready.");
        router.refresh();
      })
      .catch((reconcileError) => {
        if (!active) return;
        setError(true);
        setMessage(reconcileError.message);
      });
    return () => { active = false; };
  }, [router, sessionId]);

  return (
    <p className={`mt-5 rounded-xl border p-4 ${
      error
        ? "border-amber-800/60 bg-amber-950/20 text-amber-300"
        : "border-green-800/60 bg-green-950/20 text-green-300"
    }`}>
      {message}
    </p>
  );
}
