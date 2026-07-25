import SiteFooter from "../components/SiteFooter";
import SiteHeader from "../components/SiteHeader";

export const metadata = { title: "Changelog — StreamClip" };

const entries = [
  ["2026-07-25", "Production foundations", "Added worker heartbeat/status visibility, atomic credit reservations, billing-ready ledger, compliance pages, and first-run onboarding architecture."],
  ["2026-07-24", "Timeline editor", "Added vertical proxy editing, waveform, adjustable automatic cuts, zoom, instant edit preview, and one-pass final revision export."],
  ["2026-07-24", "Faster progressive batches", "Bounded CPU concurrency now publishes each verified clip as soon as it passes QA while the remaining cards continue processing."],
  ["2026-07-23", "Evidence-gated quality", "Added ordered setup/payoff verification, speaker-role rejection, archetype duration budgets, and final media/OCR shipping QA."],
];

export default function ChangelogPage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-6 py-20">
        <h1 className="text-5xl font-black">Changelog</h1>
        <div className="mt-10 space-y-8">
          {entries.map(([date, title, copy]) => (
            <article key={date + title} className="border-l-2 border-purple-700 pl-6">
              <p className="text-xs font-black uppercase text-purple-300">{date}</p>
              <h2 className="mt-2 text-2xl font-black">{title}</h2>
              <p className="mt-2 leading-7 text-gray-400">{copy}</p>
            </article>
          ))}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
