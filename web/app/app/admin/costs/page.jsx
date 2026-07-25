import { notFound } from "next/navigation";
import { serverClient } from "../../../lib/supabase";
import { collectCosts, founderProfile } from "../../../lib/costs";
import CostsView from "./CostsView";

// House financials are never cached or statically rendered.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function CostsPage() {
  const sb = await serverClient();
  const profile = await founderProfile(sb);
  // 404, not 403: a non-founder should not learn this route exists.
  if (!profile) notFound();

  return <CostsView profile={profile} data={await collectCosts(Date.now())} />;
}
