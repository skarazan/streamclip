import Link from "next/link";
import SiteFooter from "../components/SiteFooter";
import SiteHeader from "../components/SiteHeader";
import TwitchLoginButton from "../components/TwitchLoginButton";

const ERRORS = {
  oauth_denied: "Twitch authorization was cancelled. Nothing was connected.",
  session_failed: "We could not finish the Twitch session. Please try again.",
};

export const metadata = { title: "Connect Twitch — StreamClip" };

export default async function LoginPage({ searchParams }) {
  const query = await searchParams;
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-lg px-6 py-24 text-center">
        <h1 className="text-4xl font-black">Connect your Twitch</h1>
        <p className="mt-4 text-gray-400">
          Twitch OAuth is the only sign-in. StreamClip can process only VODs
          belonging to the connected channel.
        </p>
        {query?.error && (
          <p className="mt-6 rounded-xl border border-red-900/60 bg-red-950/20 p-3 text-sm text-red-300">
            {ERRORS[query.error] || "Sign-in failed. Please try again."}
          </p>
        )}
        <div className="mt-8">
          <TwitchLoginButton className="w-full py-4 text-lg" />
        </div>
        <p className="mt-5 text-xs leading-5 text-gray-500">
          By continuing, you agree to the{" "}
          <Link href="/legal/terms" className="text-purple-300">Terms</Link>
          {" "}and acknowledge the{" "}
          <Link href="/legal/privacy" className="text-purple-300">Privacy Policy</Link>.
        </p>
      </main>
      <SiteFooter />
    </>
  );
}
