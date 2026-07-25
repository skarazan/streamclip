import crypto from "node:crypto";

export const STRIPE_API = "https://api.stripe.com/v1";

export const PRODUCTS = {
  starter: {
    mode: "subscription",
    price: () => process.env.STRIPE_PRICE_STARTER,
    credits: 8,
    plan: "starter",
  },
  creator: {
    mode: "subscription",
    price: () => process.env.STRIPE_PRICE_CREATOR,
    credits: 20,
    plan: "creator",
  },
  credit_1: {
    mode: "payment",
    price: () => process.env.STRIPE_PRICE_CREDIT_1,
    credits: 1,
    plan: null,
  },
  credit_5: {
    mode: "payment",
    price: () => process.env.STRIPE_PRICE_CREDIT_5,
    credits: 5,
    plan: null,
  },
};

export async function stripeRequest(path, fields = {}, method = "POST") {
  if (!process.env.STRIPE_SECRET_KEY) {
    throw new Error("Stripe is not configured");
  }
  const body = new URLSearchParams();
  for (const [key, value] of Object.entries(fields)) {
    if (value != null) body.set(key, String(value));
  }
  const response = await fetch(`${STRIPE_API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${process.env.STRIPE_SECRET_KEY}`,
      ...(method === "POST"
        ? { "Content-Type": "application/x-www-form-urlencoded" }
        : {}),
    },
    body: method === "POST" ? body : undefined,
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.error?.message || "Stripe request failed");
  }
  return data;
}

export function verifyStripeSignature(rawBody, signatureHeader) {
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!secret || !signatureHeader) return false;
  const parts = Object.fromEntries(
    signatureHeader.split(",").map((part) => {
      const [key, value] = part.split("=", 2);
      return [key, value];
    })
  );
  const timestamp = Number(parts.t);
  if (!timestamp || Math.abs(Date.now() / 1000 - timestamp) > 300) return false;
  const expected = crypto
    .createHmac("sha256", secret)
    .update(`${timestamp}.${rawBody}`)
    .digest("hex");
  const received = parts.v1 || "";
  if (expected.length !== received.length) return false;
  return crypto.timingSafeEqual(
    Buffer.from(expected, "utf8"),
    Buffer.from(received, "utf8")
  );
}
