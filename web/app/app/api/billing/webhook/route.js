import { NextResponse } from "next/server";
import { rest, serviceHeaders } from "../../../../lib/editJobs";
import { stripeRequest, verifyStripeSignature } from "../../../../lib/stripe";

async function serviceFetch(path, options = {}) {
  return fetch(rest(path), {
    ...options,
    headers: serviceHeaders(options.headers || {}),
    cache: "no-store",
  });
}

async function grant({ userId, credits, reason, externalId, plan, customer }) {
  const response = await serviceFetch("/rpc/grant_credits", {
    method: "POST",
    body: JSON.stringify({
      p_user: userId,
      p_amount: Number(credits || 0),
      p_reason: reason,
      p_external_id: externalId,
      p_plan: plan || null,
      p_stripe_customer: customer || null,
    }),
  });
  if (!response.ok) throw new Error("credit ledger update failed");
}

async function subscriptionMetadata(subscriptionId) {
  if (!subscriptionId) return {};
  const subscription = await stripeRequest(
    `/subscriptions/${subscriptionId}`,
    {},
    "GET"
  );
  return subscription.metadata || {};
}

export async function POST(request) {
  const rawBody = await request.text();
  if (!verifyStripeSignature(
    rawBody,
    request.headers.get("stripe-signature")
  )) {
    return NextResponse.json({ error: "invalid signature" }, { status: 400 });
  }
  const event = JSON.parse(rawBody);
  const existing = await serviceFetch(
    `/billing_events?stripe_event_id=eq.${event.id}&select=status`
  ).then((response) => response.json());
  if (existing?.[0]?.status === "processed") {
    return NextResponse.json({ received: true, duplicate: true });
  }
  await serviceFetch("/billing_events?on_conflict=stripe_event_id", {
    method: "POST",
    headers: { Prefer: "resolution=merge-duplicates,return=minimal" },
    body: JSON.stringify({
      stripe_event_id: event.id,
      event_type: event.type,
      status: "processing",
      error: null,
    }),
  });

  try {
    const object = event.data?.object || {};
    if (event.type === "checkout.session.completed") {
      const meta = object.metadata || {};
      if (meta.product?.startsWith("credit_")) {
        await grant({
          userId: meta.user_id || object.client_reference_id,
          credits: meta.credits,
          reason: `Stripe credit pack (${meta.product})`,
          externalId: `stripe-checkout:${object.id}`,
          customer: object.customer,
        });
      } else if (meta.plan) {
        // Recurring credits are granted by invoice.paid. This call records
        // customer/plan without double-granting the first invoice.
        await grant({
          userId: meta.user_id || object.client_reference_id,
          credits: 0,
          reason: `Stripe subscription (${meta.plan})`,
          externalId: `stripe-subscription:${object.subscription}`,
          plan: meta.plan,
          customer: object.customer,
        });
      }
    } else if (event.type === "invoice.paid") {
      const meta = await subscriptionMetadata(object.subscription);
      if (meta.user_id) {
        await grant({
          userId: meta.user_id,
          credits: meta.credits,
          reason: `Monthly ${meta.plan || "subscription"} credits`,
          externalId: `stripe-invoice:${object.id}`,
          plan: meta.plan,
          customer: object.customer,
        });
      }
    } else if (
      event.type === "customer.subscription.deleted" ||
      event.type === "invoice.payment_failed"
    ) {
      const customer = object.customer;
      const status = event.type === "customer.subscription.deleted"
        ? "cancelled"
        : "past_due";
      await serviceFetch(`/users?stripe_customer_id=eq.${customer}`, {
        method: "PATCH",
        body: JSON.stringify({
          subscription_status: status,
          ...(status === "cancelled" ? { plan: "churned" } : {}),
        }),
      });
    }
    await serviceFetch(`/billing_events?stripe_event_id=eq.${event.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: "processed",
        processed_at: new Date().toISOString(),
      }),
    });
    return NextResponse.json({ received: true });
  } catch (error) {
    await serviceFetch(`/billing_events?stripe_event_id=eq.${event.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "failed", error: error.message }),
    });
    return NextResponse.json({ error: "webhook processing failed" }, { status: 500 });
  }
}
