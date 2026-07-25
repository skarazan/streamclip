import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { NextResponse } from "next/server";
import { serverClient } from "../../../../../lib/supabase";
import { rest, serviceHeaders } from "../../../../../lib/editJobs";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const s3 = new S3Client({
  region: "auto",
  endpoint: process.env.R2_ENDPOINT,
  credentials: {
    accessKeyId: process.env.R2_KEY,
    secretAccessKey: process.env.R2_SECRET,
  },
});

export async function GET(request, { params }) {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const rows = await fetch(
    rest(`/jobs?id=eq.${params.id}&user_id=eq.${user.id}&select=progress`),
    { headers: serviceHeaders(), cache: "no-store" }
  ).then((response) => response.json());
  const progress = rows?.[0]?.progress;
  const key = progress?.proxy_key || progress?.r2_key;
  if (!key) {
    return NextResponse.json({ error: "preview not ready" }, { status: 404 });
  }

  const range = request.headers.get("range") || undefined;
  try {
    const object = await s3.send(new GetObjectCommand({
      Bucket: process.env.R2_BUCKET,
      Key: key,
      Range: range,
    }));
    const headers = new Headers({
      "Accept-Ranges": object.AcceptRanges || "bytes",
      "Cache-Control": "private, max-age=3600",
      "Content-Type": object.ContentType || "video/mp4",
    });
    if (object.ContentLength != null) {
      headers.set("Content-Length", String(object.ContentLength));
    }
    if (object.ContentRange) {
      headers.set("Content-Range", object.ContentRange);
    }
    if (object.ETag) {
      headers.set("ETag", object.ETag);
    }

    return new Response(object.Body.transformToWebStream(), {
      status: object.ContentRange ? 206 : 200,
      headers,
    });
  } catch (error) {
    const status = error?.$metadata?.httpStatusCode;
    if (status === 416) {
      return new Response(null, { status: 416 });
    }
    console.error("editor media stream failed", error);
    return NextResponse.json(
      { error: "preview stream unavailable" },
      { status: 502 }
    );
  }
}
