import { redirect } from "next/navigation";
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { serverClient } from "../../lib/supabase";
import ActiveJobs from "./ActiveJobs";
import ClipCount from "./ClipCount";
import ClipVod from "./ClipVod";

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

  const [{ data: profile }, { data: clips }, { data: history }] = await Promise.all([
    sb.from("users").select("*").eq("id", user.id).single(),
    sb.from("clips").select("*").eq("user_id", user.id)
      .order("created_at", { ascending: false }),
    sb.from("jobs").select("id, vod_url, status, created_at, finished_at")
      .eq("user_id", user.id).in("status", ["done", "failed"])
      .order("created_at", { ascending: false }).limit(10),
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
        <div className="flex items-center gap-5">
          <ClipCount initial={profile?.clips_per_stream} />
          <div className="text-sm font-bold px-4 py-2 rounded-full border border-[#2e2e4a] bg-[#15151f]">
            ⚡ {profile?.credits ?? 0} GW
          </div>
        </div>
      </div>

      <ClipVod />

      <ActiveJobs />

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
      {(history || []).length > 0 && (
        <div className="mt-14">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wide mb-3">
            Processed streams
          </h2>
          <div className="rounded-2xl border border-[#23233a] bg-[#12121a] divide-y divide-[#1c1c2e]">
            {history.map((h) => {
              const n = (clips || []).filter((c) => c.job_id === h.id).length;
              return (
                <div key={h.id} className="flex items-center justify-between px-5 py-3 text-sm">
                  <a href={h.vod_url} target="_blank" className="text-purple-300 hover:underline">
                    {h.vod_url.replace("https://www.", "")}
                  </a>
                  <div className="flex items-center gap-4">
                    <span className="text-gray-400">
                      {new Date(h.finished_at || h.created_at).toLocaleString()}
                    </span>
                    {h.status === "done" ? (
                      <span className="text-green-400 font-semibold">{n} clips</span>
                    ) : (
                      <span className="text-red-400 font-semibold">failed</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </main>
  );
}
