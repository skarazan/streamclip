"use client";

import { useState } from "react";

export default function CheckoutButton({ product, children, className = "" }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const checkout = async () => {
    setBusy(true);
    setError("");
    window.plausible?.("Checkout Started", { props: { product } });
    try {
      const response = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Checkout failed");
      window.location.assign(data.url);
    } catch (checkoutError) {
      setError(checkoutError.message);
      setBusy(false);
    }
  };
  return (
    <div>
      <button
        type="button"
        onClick={checkout}
        disabled={busy}
        className={`w-full rounded-xl bg-[#9146FF] px-5 py-3 font-black text-white hover:bg-[#7a2ff0] disabled:opacity-60 ${className}`}
      >
        {busy ? "Opening checkout…" : children}
      </button>
      {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
    </div>
  );
}
