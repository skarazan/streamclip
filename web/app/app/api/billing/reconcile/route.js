import { NextResponse } from "next/server";
import { serverClient } from "../../../../lib/supabase";
import {
  fulfillCheckoutSession, fulfillPaidInvoice, subscriptionDetails,
} from "../../../../lib/billing";
import { stripeRequest } from "../../../../lib/stripe";

export async function POST(request) {
  const sb = await serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await request.json().catch(() => ({}));
  const sessionId = String(body.session_id || "");
  if (!sessionId.startsWith("cs_")) {
    return NextResponse.json({ error: "invalid checkout session" }, { status: 400 });
  }

  try {
    const session = await stripeRequest(
      `/checkout/sessions/${encodeURIComponent(sessionId)}?expand[]=subscription`,
      {},
      "GET"
    );
    const sessionUser = session.metadata?.user_id || session.client_reference_id;
    if (sessionUser !== user.id) {
      return NextResponse.json({ error: "checkout session not found" }, { status: 404 });
    }
    if (session.status !== "complete" ||
        !["paid", "no_payment_required"].includes(session.payment_status)) {
      return NextResponse.json({ error: "payment is not complete" }, { status: 409 });
    }

    await fulfillCheckoutSession(session);
    if (session.mode === "subscription") {
      const subscription = await subscriptionDetails(session.subscription);
      const invoiceId = typeof subscription?.latest_invoice === "object"
        ? subscription.latest_invoice.id
        : subscription?.latest_invoice;
      if (invoiceId) {
        await fulfillPaidInvoice({
          id: invoiceId,
          customer: session.customer,
          subscription: subscription.id,
        }, subscription);
      }
    }
    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Stripe checkout reconciliation failed", error);
    return NextResponse.json(
      { error: error.message === "billing database migration is not installed"
          ? "Billing setup is finishing. Please try again shortly."
          : "Could not confirm the payment yet. Please try again shortly." },
      { status: 503 }
    );
  }
}
