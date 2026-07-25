import Link from "next/link";
import SiteFooter from "./components/SiteFooter";
import SiteHeader from "./components/SiteHeader";
import TwitchLoginButton from "./components/TwitchLoginButton";

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-6 py-20 lg:grid-cols-[1.1fr_.9fr] lg:py-28">
          <div>
            <p className="inline-block rounded-full border border-[#2e2e4a] bg-[#15151f] px-3 py-1 text-xs font-semibold text-purple-300">
              Built for Twitch gaming streamers
            </p>
            <h1 className="mt-6 text-5xl font-black leading-[1.02] tracking-tight md:text-7xl">
              Your community already marks the funny moments.
            </h1>
            <p className="mt-6 max-w-2xl text-lg text-gray-400">
              StreamClip turns those moments into arc-verified, captioned
              vertical Shorts while you sleep—even when your channel is still
              too small to generate viewer clips.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <TwitchLoginButton className="px-8 py-4 text-lg" />
              <Link href="/demo" className="rounded-xl border border-[#343451] px-6 py-4 font-bold">
                See how clips are chosen
              </Link>
            </div>
            <p className="mt-4 text-xs text-gray-500">
              Two VOD credits free · no card · your channel&apos;s content only
            </p>
          </div>
          <div className="mx-auto w-full max-w-sm rounded-[2rem] border border-purple-800/60 bg-[#111119] p-4 shadow-2xl shadow-purple-950/50">
            <div className="aspect-[9/16] rounded-2xl bg-gradient-to-b from-[#261645] via-[#12121c] to-black p-6">
              <div className="rounded-full bg-black/50 px-3 py-2 text-center text-xs font-black uppercase">
                The joke that broke his whole run
              </div>
              <div className="flex h-full flex-col items-center justify-center text-center">
                <p className="text-6xl">⚡</p>
                <p className="mt-4 text-2xl font-black">Setup → payoff verified</p>
                <p className="mt-2 text-sm text-gray-400">
                  No random yelling. No ten-second dead zone. No ending before
                  the punchline.
                </p>
              </div>
            </div>
          </div>
        </section>
        <section className="border-y border-[#1c1c2e] bg-[#0d0d14]">
          <div className="mx-auto grid max-w-6xl gap-6 px-6 py-16 md:grid-cols-3">
            {[
              ["1", "Connect Twitch", "Authorize your own channel once. No passwords and no stranger’s VODs."],
              ["2", "Just stream", "Crowd evidence, chat, audio, and AI find complete stories after you go offline."],
              ["3", "Wake up to clips", "Verified 9:16 Shorts appear progressively, ready to watch, fix, and post."],
            ].map(([number, title, copy]) => (
              <article key={number} className="rounded-2xl border border-[#23233a] bg-[#12121a] p-6">
                <p className="text-sm font-black text-purple-300">{number}</p>
                <h2 className="mt-3 text-xl font-black">{title}</h2>
                <p className="mt-2 text-sm leading-6 text-gray-400">{copy}</p>
              </article>
            ))}
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
