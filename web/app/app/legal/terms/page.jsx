import SiteFooter from "../../components/SiteFooter";
import SiteHeader from "../../components/SiteHeader";

export const metadata = { title: "Terms of Service — StreamClip" };

export default function TermsPage() {
  return (
    <>
      <SiteHeader />
      <main className="legal-copy mx-auto max-w-3xl px-6 py-20">
        <h1>Terms of Service</h1>
        <p>Effective July 25, 2026. These launch terms should be reviewed by qualified counsel before accepting paid production customers.</p>
        <h2>Service</h2>
        <p>StreamClip processes authorized Twitch VODs into suggested short-form video files. Automated selection is probabilistic; a VOD credit purchases one scan, not a guaranteed number of outputs, views, revenue, or platform acceptance.</p>
        <h2>Your content and authorization</h2>
        <p>You retain ownership of your content. You represent that you own or have permission to process and publish every stream submitted. StreamClip may refuse VODs that do not belong to the connected Twitch channel.</p>
        <h2>Acceptable use</h2>
        <p>Do not use the service for unlawful content, harassment, infringement, deceptive impersonation, malware, abuse of trials, or attempts to access another customer’s data or media.</p>
        <h2>Credits, billing, cancellation, and refunds</h2>
        <p>Credits are consumed by VOD processing as described on the pricing page. Subscriptions renew until cancelled through the billing portal. Unused monthly credits do not roll over unless a plan explicitly says otherwise. Failed internal processing is refunded automatically. Other refund requests are evaluated at support@streamclip.app where required by law.</p>
        <h2>Availability and changes</h2>
        <p>The service may be delayed or unavailable. We may change features or limits to protect reliability, security, or unit economics, with reasonable notice for material paid-plan changes.</p>
        <h2>Disclaimers and liability</h2>
        <p>The service is provided “as is” to the maximum extent permitted by law. StreamClip is not responsible for platform moderation, copyright claims arising from your content, lost audience revenue, or indirect damages. Aggregate liability is limited to fees paid during the previous three months where such a limit is lawful.</p>
        <h2>Contact</h2>
        <p>Questions or legal notices: support@streamclip.app.</p>
      </main>
      <SiteFooter />
    </>
  );
}
