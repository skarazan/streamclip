import { NextResponse } from "next/server";
import { readServiceHealth } from "../../../lib/serviceHealth";

export const dynamic = "force-dynamic";

export async function GET() {
  const health = await readServiceHealth();
  return NextResponse.json(health, {
    status: health.state === "unknown" ? 503 : 200,
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
