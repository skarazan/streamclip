import Link from "next/link";
import { serverClient } from "../../lib/supabase";

export default async function SiteHeader() {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  return (
    <header className="border-b border-[#1c1c2e] bg-[#0a0a0f]/90 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="text-xl font-black">
          Stream<span className="text-[#9146FF]">Clip</span>
        </Link>
        <div className="flex items-center gap-4 text-sm font-semibold text-gray-300">
          <Link href="/demo" className="hidden hover:text-white sm:block">Demo</Link>
          <Link href="/pricing" className="hidden hover:text-white sm:block">Pricing</Link>
          <Link href="/faq" className="hidden hover:text-white md:block">FAQ</Link>
          <Link href="/status" className="hidden hover:text-white md:block">Status</Link>
          <Link
            href={user ? "/app" : "/login"}
            className="rounded-lg bg-[#9146FF] px-4 py-2 font-black text-white hover:bg-[#7a2ff0]"
          >
            {user ? "Open dashboard" : "Connect Twitch"}
          </Link>
        </div>
      </nav>
    </header>
  );
}
