import { NextResponse } from "next/server";
import { serverClient } from "../../../../lib/supabase";
import { rest, serviceHeaders } from "../../../../lib/editJobs";
import { stripeRequest } from "../../../../lib/stripe";

export async function POST(request) {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const profiles = await fetch(
    rest(`/users?id=eq.${user.id}&select=stripe_customer_id`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((response) => response.json());
  const customer = profiles?.[0]?.stripe_customer_id;
  if (!customer) {
    return NextResponse.json({ error: "No billing account yet." }, { status: 404 });
  }
  try {
    const origin = new URL(request.url).origin;
    const session = await stripeRequest("/billing_portal/sessions", {
      customer,
      return_url: `${origin}/app/billing`,
    });
    return NextResponse.json({ url: session.url });
  } catch (error) {
    return NextResponse.json({ error: error.message }, { status: 502 });
  }
}
