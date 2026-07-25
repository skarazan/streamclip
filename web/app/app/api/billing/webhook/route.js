import { NextResponse } from "next/server";
import {
  billingServiceFetch, fulfillCheckoutSession, fulfillPaidInvoice,
} from "../../../../lib/billing";
import { verifyStripeSignature } from "../../../../lib/stripe";

export async function POST(request) {
  const rawBody = await request.text();
  if (!verifyStripeSignature(
    rawBody,
    request.headers.get("stripe-signature")
  )) {
    return NextResponse.json({ error: "invalid signature" }, { status: 400 });
  }
  const event = JSON.parse(rawBody);
  const existing = await billingServiceFetch(
    `/billing_events?stripe_event_id=eq.${event.id}&select=status`
  ).then((response) => response.json());
  if (existing?.[0]?.status === "processed") {
    return NextResponse.json({ received: true, duplicate: true });
  }
  await billingServiceFetch("/billing_events?on_conflict=stripe_event_id", {
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
      // Recurring credits are granted by invoice.paid. This records the
      // customer/plan without double-granting the first invoice.
      await fulfillCheckoutSession(object);
    } else if (event.type === "invoice.paid") {
      await fulfillPaidInvoice(object);
    } else if (
      event.type === "customer.subscription.deleted" ||
      event.type === "invoice.payment_failed"
    ) {
      const customer = object.customer;
      const status = event.type === "customer.subscription.deleted"
        ? "cancelled"
        : "past_due";
      await billingServiceFetch(`/users?stripe_customer_id=eq.${customer}`, {
        method: "PATCH",
        body: JSON.stringify({
          subscription_status: status,
          ...(status === "cancelled" ? { plan: "churned" } : {}),
        }),
      });
    }
    await billingServiceFetch(`/billing_events?stripe_event_id=eq.${event.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: "processed",
        processed_at: new Date().toISOString(),
      }),
    });
    return NextResponse.json({ received: true });
  } catch (error) {
    await billingServiceFetch(`/billing_events?stripe_event_id=eq.${event.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "failed", error: error.message }),
    });
    return NextResponse.json({ error: "webhook processing failed" }, { status: 500 });
  }
}
