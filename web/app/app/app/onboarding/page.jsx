import { redirect } from "next/navigation";
import { serverClient } from "../../../lib/supabase";
import OnboardingForm from "./OnboardingForm";

export const metadata = { title: "First clip setup — StreamClip" };

export default async function OnboardingPage() {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) redirect("/login");
  const { count } = await sb.from("jobs")
    .select("id", { count: "exact", head: true })
    .eq("user_id", user.id);
  if (count > 0) redirect("/app");
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <p className="text-xs font-black uppercase tracking-[0.2em] text-purple-300">First-run setup</p>
      <h1 className="mt-3 text-5xl font-black">From Twitch to first clip.</h1>
      <p className="mt-4 text-gray-400">Pick the packaging once. Selection and story verification stay automatic.</p>
      <OnboardingForm />
    </main>
  );
}
