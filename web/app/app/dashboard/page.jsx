import { redirect } from "next/navigation";
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { serverClient } from "../../lib/supabase";

const s3 = new S3Client({
  region: "auto",
  endpoint: process.env.R2_ENDPOINT,
  credentials: {
    accessKeyId: process.env.R2_KEY,
    secretAccessKey: process.env.R2_SECRET,
  },
});

async function signed(key) {
  return getSignedUrl(
    s3,
    new GetObjectCommand({ Bucket: process.env.R2_BUCKET, Key: key }),
    { expiresIn: 3600 }
  );
}

export default async function Dashboard() {
  const sb = serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) redirect("/");

  const [{ data: profile }, { data: clips }] = await Promise.all([
    sb.from("users").select("*").eq("id", user.id).single(),
    sb.from("clips").select("*").eq("user_id", user.id)
      .order("created_at", { ascending: false }),
  ]);

  const withUrls = await Promise.all(
    (clips || []).map(async (c) => ({ ...c, url: await signed(c.r2_key) }))
  );

  return (
    <main className="max-w-6xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-10">
        <div className="text-xl font-black">
          Stream<span className="text-[#9146FF]">Clip</span>
          <span className="ml-3 text-sm font-normal text-gray-400">
            {profile?.twitch_login}
          </span>
        </div>
        <div className="text-sm font-bold px-4 py-2 rounded-full border border-[#2e2e4a] bg-[#15151f]">
          ⚡ {profile?.credits ?? 0} credits
        </div>
      </div>

      {withUrls.length === 0 ? (
        <div className="text-center py-24 text-gray-400">
          <p className="text-2xl font-bold mb-2">No clips yet</p>
          <p>Your next stream gets clipped automatically. Just go live.</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {withUrls.map((c) => (
            <div key={c.id}
                 className="rounded-2xl p-4 border border-[#23233a] bg-[#12121a]">
              <video src={c.url} controls preload="metadata"
                     className="rounded-xl w-full aspect-[9/16] object-cover bg-black" />
              <div className="flex items-start justify-between mt-3 gap-2">
                <div>
                  <p className="font-bold leading-snug">{c.title}</p>
                  {c.hook && <p className="text-xs text-gray-400 mt-1">{c.hook}</p>}
                </div>
                <span className="shrink-0 text-xs font-black px-2 py-1 rounded-lg bg-[#9146FF]/20 text-purple-300">
                  {Number(c.score).toFixed(0)}/10
                </span>
              </div>
              <a href={c.url} download
                 className="block text-center mt-3 bg-[#9146FF] hover:bg-[#7a2ff0] text-white text-sm font-bold py-2 rounded-lg">
                Download
              </a>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
