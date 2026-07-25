import SiteFooter from "../../components/SiteFooter";
import SiteHeader from "../../components/SiteHeader";

export const metadata = { title: "Cookie Policy — StreamClip" };

export default function CookiesPage() {
  return (
    <>
      <SiteHeader />
      <main className="legal-copy mx-auto max-w-3xl px-6 py-20">
        <h1>Cookie Policy</h1>
        <p>Effective July 25, 2026.</p>
        <h2>Strictly necessary storage</h2>
        <p>StreamClip uses Supabase authentication cookies to keep you signed in, protect authenticated routes, and complete Twitch OAuth. The service cannot provide an account dashboard without them.</p>
        <h2>Analytics</h2>
        <p>The launch architecture permits cookieless, aggregate analytics such as Plausible. We do not use Google Analytics or advertising cookies. If non-essential cookies are introduced later, consent controls will appear before they are set where required.</p>
        <h2>Controls</h2>
        <p>You can clear cookies through your browser. Clearing the authentication cookie signs you out. Browser privacy controls do not affect server-side job and billing records; use account deletion for those.</p>
      </main>
      <SiteFooter />
    </>
  );
}
