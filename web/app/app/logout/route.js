import { NextResponse } from "next/server";
import { serverClient } from "../../lib/supabase";

export async function GET(request) {
  const sb = serverClient();
  await sb.auth.signOut();
  return NextResponse.redirect(new URL("/", request.url));
}
