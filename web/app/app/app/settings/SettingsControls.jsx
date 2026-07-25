"use client";

import { useState } from "react";

export default function SettingsControls({ initialNotifications, deletionAt }) {
  const [notifications, setNotifications] = useState(initialNotifications);
  const [scheduled, setScheduled] = useState(deletionAt);
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const saveNotifications = async (next) => {
    setNotifications(next);
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notification_email: next }),
    });
    if (!response.ok) {
      setNotifications(!next);
      setMessage("Notification preference could not be saved.");
    } else setMessage("Notification preference saved.");
  };

  const accountAction = async (action) => {
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, confirmation }),
    });
    const data = await response.json();
    if (response.ok) {
      setScheduled(data.deletion_requested_at);
      setConfirmation("");
      setMessage(action === "schedule_deletion"
        ? "Deletion scheduled. You have seven days to cancel."
        : "Account deletion cancelled.");
    } else setMessage(data.error || "Account update failed.");
    setBusy(false);
  };

  return (
    <div className="space-y-8">
      <section className="rounded-2xl border border-[#282840] bg-[#12121a] p-6">
        <h2 className="text-xl font-black">Notifications</h2>
        <label className="mt-4 flex cursor-pointer items-center justify-between gap-4">
          <span><span className="font-bold">Clip-ready email</span><span className="block text-sm text-gray-500">Receive one message when a batch finishes.</span></span>
          <input type="checkbox" checked={notifications} onChange={(event) => saveNotifications(event.target.checked)}
            className="h-5 w-5 accent-[#9146FF]" />
        </label>
      </section>
      <section className="rounded-2xl border border-red-900/60 bg-red-950/10 p-6">
        <h2 className="text-xl font-black text-red-200">Danger zone</h2>
        {scheduled ? (
          <>
            <p className="mt-3 text-sm text-red-200/80">
              Deletion is scheduled for {new Date(scheduled).toLocaleString()}.
              Your database rows and stored media will be removed after the
              seven-day recovery window.
            </p>
            <button type="button" disabled={busy} onClick={() => accountAction("cancel_deletion")}
              className="mt-5 rounded-xl bg-white px-5 py-3 font-black text-black">
              Cancel account deletion
            </button>
          </>
        ) : (
          <>
            <p className="mt-3 text-sm text-gray-400">
              Type DELETE to schedule permanent account and media deletion.
            </p>
            <input value={confirmation} onChange={(event) => setConfirmation(event.target.value)}
              className="mt-4 w-full rounded-xl border border-red-900/60 bg-black/30 px-4 py-3"
              placeholder="DELETE" />
            <button type="button" disabled={busy || confirmation !== "DELETE"}
              onClick={() => accountAction("schedule_deletion")}
              className="mt-3 rounded-xl bg-red-700 px-5 py-3 font-black disabled:opacity-50">
              Schedule deletion
            </button>
          </>
        )}
      </section>
      {message && <p className="text-sm text-gray-300">{message}</p>}
    </div>
  );
}
