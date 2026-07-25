import { rest, serviceHeaders } from "./editJobs";
import { stripeRequest } from "./stripe";

export async function billingServiceFetch(path, options = {}) {
  return fetch(rest(path), {
    ...options,
    headers: serviceHeaders(options.headers || {}),
    cache: "no-store",
  });
}

export async function grantCredits({
  userId, credits, reason, externalId, plan, customer,
}) {
  const response = await billingServiceFetch("/rpc/grant_credits", {
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
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    if (response.status === 404 || error?.code === "PGRST202") {
      throw new Error("billing database migration is not installed");
    }
    throw new Error("credit ledger update failed");
  }
  return response.json();
}

export async function subscriptionDetails(subscription) {
  if (!subscription) return null;
  if (typeof subscription === "object" && subscription.metadata) {
    return subscription;
  }
  return stripeRequest(`/subscriptions/${subscription}`, {}, "GET");
}

export async function fulfillCheckoutSession(session) {
  const meta = session.metadata || {};
  const userId = meta.user_id || session.client_reference_id;
  if (!userId) throw new Error("checkout session has no user");

  if (meta.product?.startsWith("credit_")) {
    return grantCredits({
      userId,
      credits: meta.credits,
      reason: `Stripe credit pack (${meta.product})`,
      externalId: `stripe-checkout:${session.id}`,
      customer: session.customer,
    });
  }

  if (meta.plan) {
    await grantCredits({
      userId,
      credits: 0,
      reason: `Stripe subscription (${meta.plan})`,
      externalId: `stripe-subscription:${
        typeof session.subscription === "object"
          ? session.subscription.id
          : session.subscription
      }`,
      plan: meta.plan,
      customer: session.customer,
    });
  }
  return null;
}

export async function fulfillPaidInvoice(invoice, subscription = null) {
  const details = await subscriptionDetails(
    subscription || invoice.subscription
  );
  const meta = details?.metadata || {};
  if (!meta.user_id) return null;
  return grantCredits({
    userId: meta.user_id,
    credits: meta.credits,
    reason: `Monthly ${meta.plan || "subscription"} credits`,
    externalId: `stripe-invoice:${invoice.id}`,
    plan: meta.plan,
    customer: invoice.customer,
  });
}
