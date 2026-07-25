import { NextResponse } from "next/server";
import { serverClient } from "../../../../lib/supabase";
import { rest, serviceHeaders } from "../../../../lib/editJobs";
import { PRODUCTS, stripeRequest } from "../../../../lib/stripe";

export async function POST(request) {
  const sb = await serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const body = await request.json().catch(() => ({}));
  const product = PRODUCTS[body.product];
  if (!product || !product.price()) {
    return NextResponse.json(
      { error: "This purchase option is not configured yet." },
      { status: 503 }
    );
  }
  const profiles = await fetch(
    rest(`/users?id=eq.${user.id}&select=stripe_customer_id`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((response) => response.json());
  const profile = profiles?.[0] || {};
  const origin = new URL(request.url).origin;
  const fields = {
    mode: product.mode,
    "line_items[0][price]": product.price(),
    "line_items[0][quantity]": 1,
    success_url: `${origin}/app/billing?checkout=success`,
    cancel_url: `${origin}/pricing?checkout=cancelled`,
    client_reference_id: user.id,
    "metadata[user_id]": user.id,
    "metadata[product]": body.product,
    "metadata[credits]": product.credits,
    "metadata[plan]": product.plan || "",
    allow_promotion_codes: "true",
  };
  if (profile.stripe_customer_id) {
    fields.customer = profile.stripe_customer_id;
  } else if (user.email) {
    fields.customer_email = user.email;
  }
  if (product.mode === "subscription") {
    fields["subscription_data[metadata][user_id]"] = user.id;
    fields["subscription_data[metadata][credits]"] = product.credits;
    fields["subscription_data[metadata][plan]"] = product.plan;
  }
  try {
    const session = await stripeRequest("/checkout/sessions", fields);
    return NextResponse.json({ url: session.url });
  } catch (error) {
    return NextResponse.json({ error: error.message }, { status: 502 });
  }
}
