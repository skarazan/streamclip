import SiteFooter from "../components/SiteFooter";
import SiteHeader from "../components/SiteHeader";

export const metadata = {
  title: "FAQ — StreamClip",
  description: "How StreamClip selects, verifies, edits, and bills Twitch VOD clips.",
};

const faqs = [
  ["How are moments selected?", "Viewer clips and chat activity nominate moments when available. Audio and transcript signals cover small channels. An AI editor proposes the story, but timestamped setup and payoff evidence must verify before a clip ships."],
  ["What if my channel has almost no viewers?", "That is a core use case. StreamClip’s Tier C path uses transcript, voice-energy change, chat when present, and story verification without requiring community clips."],
  ["Does one credit guarantee five clips?", "No. One credit pays for a complete VOD scan, targeting up to five verified clips. You may request one through eight, but StreamClip ships fewer rather than inventing filler."],
  ["Can I fix a cut?", "Yes. Every delivered clip has a low-resolution timeline editor. You can extend the story, restore or resize automatic cuts, add your own cut, and perform one final 1080×1920 export."],
  ["Which platforms are supported?", "Twitch VODs are supported now. Output is formatted for YouTube Shorts, TikTok, and Reels. Kick ingestion and automatic social posting are future features."],
  ["Who owns the clips?", "You retain ownership of your stream content. StreamClip processes content from the Twitch channel you authorize and does not claim ownership."],
  ["Can I cancel or delete my data?", "Subscriptions are managed through Stripe’s billing portal. Account deletion can be scheduled from settings with a seven-day recovery window, after which database rows and R2 media are removed."],
];

export default function FAQPage() {
  const schema = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map(([question, answer]) => ({
      "@type": "Question",
      name: question,
      acceptedAnswer: { "@type": "Answer", text: answer },
    })),
  };
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-6 py-20">
        <h1 className="text-5xl font-black">Questions, answered plainly.</h1>
        <div className="mt-10 space-y-4">
          {faqs.map(([question, answer]) => (
            <details key={question} className="rounded-2xl border border-[#23233a] bg-[#12121a] p-5">
              <summary className="cursor-pointer font-black">{question}</summary>
              <p className="mt-3 leading-7 text-gray-400">{answer}</p>
            </details>
          ))}
        </div>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} />
      </main>
      <SiteFooter />
    </>
  );
}
