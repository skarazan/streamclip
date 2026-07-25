import Link from "next/link";
import CheckoutButton from "../components/CheckoutButton";
import SiteFooter from "../components/SiteFooter";
import SiteHeader from "../components/SiteHeader";
import { serverClient } from "../../lib/supabase";

export const metadata = {
  title: "Pricing — StreamClip",
  description: "VOD-credit pricing for automatic, verified Twitch Shorts.",
};

const plans = [
  {
    id: "starter",
    name: "Starter",
    price: "$14.99",
    credits: "8 VOD credits / month",
    points: ["Up to 5 verified clips per scan", "Timeline correction editor", "Caption, title, and opening templates"],
  },
  {
    id: "creator",
    name: "Creator",
    price: "$29.99",
    credits: "20 VOD credits / month",
    points: ["Everything in Starter", "Priority processing", "Higher revision allowance", "Style profiles as they ship"],
  },
];

export default async function PricingPage() {
  const sb = await serverClient();
  const { data: { user } } = await sb.auth.getUser();
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-5xl px-6 py-20">
        <div className="text-center">
          <p className="text-xs font-black uppercase tracking-[0.2em] text-purple-300">Simple usage pricing</p>
          <h1 className="mt-3 text-5xl font-black">Pay for streams, not filler clips.</h1>
          <p className="mx-auto mt-5 max-w-2xl text-gray-400">
            One credit scans one full VOD up to eight hours. Five clips is the
            target; the quality gate may ship fewer rather than pad the batch.
          </p>
        </div>
        <div className="mt-12 grid gap-6 md:grid-cols-2">
          {plans.map((plan) => (
            <article key={plan.id} className="rounded-3xl border border-[#2d2d48] bg-[#12121a] p-7">
              <h2 className="text-2xl font-black">{plan.name}</h2>
              <p className="mt-4 text-5xl font-black">{plan.price}<span className="text-base text-gray-500">/mo</span></p>
              <p className="mt-2 font-bold text-purple-300">{plan.credits}</p>
              <ul className="my-7 space-y-3 text-sm text-gray-300">
                {plan.points.map((point) => <li key={point}>✓ {point}</li>)}
              </ul>
              {user ? (
                <CheckoutButton product={plan.id}>Choose {plan.name}</CheckoutButton>
              ) : (
                <Link href="/login" className="block rounded-xl bg-[#9146FF] px-5 py-3 text-center font-black text-white">
                  Connect Twitch
                </Link>
              )}
            </article>
          ))}
        </div>
        <section className="mt-10 rounded-3xl border border-[#23233a] bg-[#0d0d14] p-7">
          <h2 className="text-xl font-black">Extra credits</h2>
          <p className="mt-2 text-sm text-gray-400">$1.99 for one or $7.99 for five. Streams over eight hours use two credits; the maximum is sixteen hours.</p>
          {user && (
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <CheckoutButton product="credit_1">Buy 1 credit · $1.99</CheckoutButton>
              <CheckoutButton product="credit_5">Buy 5 credits · $7.99</CheckoutButton>
            </div>
          )}
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
