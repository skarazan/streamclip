import SiteFooter from "../../components/SiteFooter";
import SiteHeader from "../../components/SiteHeader";

export const metadata = { title: "Privacy Policy — StreamClip" };

export default function PrivacyPage() {
  return (
    <>
      <SiteHeader />
      <main className="legal-copy mx-auto max-w-3xl px-6 py-20">
        <h1>Privacy Policy</h1>
        <p>Effective July 25, 2026. Contact support@streamclip.app for privacy requests.</p>
        <h2>Data we process</h2>
        <p>We store Twitch identity and channel identifiers, account settings, plan and credit records, VOD URLs, job diagnostics, generated clips, edit recipes, sampled chat evidence, transcripts, and billing identifiers. We do not store a StreamClip password because sign-in uses Twitch OAuth.</p>
        <h2>Why we process it</h2>
        <p>We use this data to authenticate you, process your own streams, select and render clips, provide downloads and editing, enforce credits, prevent abuse, support customers, and measure service reliability.</p>
        <h2>Processors</h2>
        <p>Current service providers may include Twitch, Supabase, Modal, Groq, Google, Anthropic, Cloudflare R2, Vercel, Stripe, Twilio, and error/uptime providers when enabled. Data is shared only as needed for their service role.</p>
        <h2>Retention</h2>
        <p>Account and billing records are kept while the account is active and as required for tax, fraud, and legal obligations. Working downloads and temporary render files are deleted after processing. Generated media and job records remain available until deletion or an announced plan retention limit.</p>
        <h2>Your rights</h2>
        <p>Depending on location, you may request access, correction, export, restriction, objection, or deletion. Account deletion has a seven-day recovery window, then database rows and media objects are removed except records legally required to be retained.</p>
        <h2>Security and international transfers</h2>
        <p>We use scoped authentication, row-level access policies, private object storage, and service credentials kept server-side. No internet service can promise absolute security. Providers may process data outside your country under their transfer mechanisms.</p>
        <h2>Children</h2>
        <p>StreamClip is not directed to children under 13 or the minimum digital-consent age in their jurisdiction.</p>
      </main>
      <SiteFooter />
    </>
  );
}
