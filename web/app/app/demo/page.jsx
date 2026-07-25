import SiteFooter from "../components/SiteFooter";
import SiteHeader from "../components/SiteHeader";

export const metadata = {
  title: "Demo — StreamClip",
  description: "See how StreamClip explains and verifies automatic clip selections.",
};

const examples = [
  ["Reaction", "The chat message that made the confidence disappear", "Keeps the read, the realization, and the comeback; removes the unrelated chat-reading tail."],
  ["Committed bit", "He doubled down until the game proved him wrong", "Preserves the setup and escalation because the punchline is confusing without both."],
  ["Jumpscare", "He knew it was coming and still wasn’t ready", "Uses the audio spike as payoff evidence when speech transcription cannot represent the scream."],
];

export default function DemoPage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-6 py-20">
        <p className="text-xs font-black uppercase tracking-[0.2em] text-purple-300">Transparent selection</p>
        <h1 className="mt-3 max-w-3xl text-5xl font-black">Not just a score. A reason the story works.</h1>
        <p className="mt-5 max-w-2xl text-gray-400">
          Real customer media remains private. These cards demonstrate the
          manifest explanation each finished batch records.
        </p>
        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {examples.map(([kind, title, why]) => (
            <article key={title} className="rounded-3xl border border-[#2b2b44] bg-[#12121a] p-4">
              <div className="grid aspect-[9/16] place-items-center rounded-2xl bg-gradient-to-b from-purple-950/70 to-black p-7 text-center">
                <div>
                  <p className="text-xs font-black uppercase tracking-widest text-purple-300">{kind}</p>
                  <h2 className="mt-4 text-2xl font-black">{title}</h2>
                </div>
              </div>
              <p className="mt-4 text-xs font-black uppercase text-gray-500">Why it shipped</p>
              <p className="mt-2 text-sm leading-6 text-gray-300">{why}</p>
            </article>
          ))}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
