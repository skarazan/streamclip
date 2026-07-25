import { redirect } from "next/navigation";
import CheckoutButton from "../../components/CheckoutButton";
import PortalButton from "../../components/PortalButton";
import { serverClient } from "../../../lib/supabase";

export const metadata = { title: "Billing — StreamClip" };

export default async function BillingPage({ searchParams }) {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) redirect("/login");
  const [{ data: profile }, { data: events }] = await Promise.all([
    sb.from("users").select("plan,credits,subscription_status,stripe_customer_id")
      .eq("id", user.id).single(),
    sb.from("credit_events").select("id,delta,reason,created_at")
      .eq("user_id", user.id).order("created_at", { ascending: false }).limit(30),
  ]);
  return (
    <main className="mx-auto max-w-4xl px-6 py-16">
      <a href="/app" className="text-sm font-bold text-purple-300">← Dashboard</a>
      <h1 className="mt-5 text-4xl font-black">Plan and credits</h1>
      {searchParams?.checkout === "success" && (
        <p className="mt-5 rounded-xl border border-green-800/60 bg-green-950/20 p-4 text-green-300">
          Payment received. Stripe is updating your ledger now.
        </p>
      )}
      <div className="mt-8 grid gap-5 sm:grid-cols-2">
        <section className="rounded-2xl border border-[#282840] bg-[#12121a] p-6">
          <p className="text-xs uppercase text-gray-500">Current plan</p>
          <p className="mt-2 text-2xl font-black capitalize">{profile?.plan || "trial"}</p>
          <p className="mt-1 text-sm text-gray-400">{profile?.subscription_status || "No paid subscription"}</p>
          <div className="mt-5"><PortalButton /></div>
        </section>
        <section className="rounded-2xl border border-[#282840] bg-[#12121a] p-6">
          <p className="text-xs uppercase text-gray-500">Available</p>
          <p className="mt-2 text-4xl font-black">⚡ {profile?.credits ?? 0}</p>
          <div className="mt-5 grid gap-2">
            <CheckoutButton product="credit_1">Add 1 credit</CheckoutButton>
            <CheckoutButton product="credit_5">Add 5 credits</CheckoutButton>
          </div>
        </section>
      </div>
      <section className="mt-8">
        <h2 className="text-xl font-black">Credit ledger</h2>
        <div className="mt-3 divide-y divide-[#24243a] rounded-2xl border border-[#24243a]">
          {(events || []).map((event) => (
            <div key={event.id} className="flex items-center justify-between px-5 py-3 text-sm">
              <div><p className="font-bold">{event.reason}</p><p className="text-xs text-gray-500">{new Date(event.created_at).toLocaleString()}</p></div>
              <span className={event.delta >= 0 ? "text-green-300" : "text-amber-300"}>{event.delta > 0 ? "+" : ""}{event.delta}</span>
            </div>
          ))}
          {!events?.length && <p className="p-5 text-sm text-gray-500">No ledger events yet.</p>}
        </div>
      </section>
    </main>
  );
}
