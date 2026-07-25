import Link from "next/link";

export default function SiteFooter() {
  return (
    <footer className="mt-20 border-t border-[#1c1c2e]">
      <div className="mx-auto grid max-w-6xl gap-8 px-6 py-10 text-sm text-gray-400 sm:grid-cols-3">
        <div>
          <p className="font-black text-white">
            Stream<span className="text-[#9146FF]">Clip</span>
          </p>
          <p className="mt-2">Your stream, clipped while you sleep.</p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Link href="/pricing">Pricing</Link>
          <Link href="/faq">FAQ</Link>
          <Link href="/demo">Demo</Link>
          <Link href="/changelog">Changelog</Link>
          <Link href="/status">Status</Link>
          <a href="mailto:support@streamclip.app">Support</a>
        </div>
        <div className="grid gap-2">
          <Link href="/legal/terms">Terms</Link>
          <Link href="/legal/privacy">Privacy</Link>
          <Link href="/legal/cookies">Cookies</Link>
          <p className="mt-2 text-xs text-gray-600">© 2026 StreamClip</p>
        </div>
      </div>
    </footer>
  );
}
