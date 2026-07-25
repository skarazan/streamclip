import { redirect } from "next/navigation";
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { serverClient } from "../../lib/supabase";
import ActiveJobs from "./ActiveJobs";
import ClipCount from "./ClipCount";
import ClipVod from "./ClipVod";
import StylePicker from "./StylePicker";
import TemplatePicker from "./TemplatePicker";
import RunAgain from "./RunAgain";
import ClipEditor from "./ClipEditor";
import ClipTimelineEditor from "./ClipTimelineEditor";
import DashboardAutoRefresh from "./DashboardAutoRefresh";
import WorkerStatusBanner from "./WorkerStatusBanner";
import ClipFeedback from "./ClipFeedback";
import ClipPlayer from "./ClipPlayer";

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
  const sb = await serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) redirect("/login");

  const [
    { data: profile },
    { data: clips },
    { data: history },
    { data: revisions },
  ] = await Promise.all([
    sb.from("users").select("*").eq("id", user.id).single(),
    sb.from("clips").select("*").eq("user_id", user.id)
      .order("r2_key", { ascending: true }),
    sb.from("jobs").select("id, vod_url, status, created_at, finished_at, progress")
      .eq("user_id", user.id).in("status", ["done", "failed", "running"])
      // Editor proxy/revision jobs are implementation details. Filtering
      // after LIMIT let enough edits push the parent stream out of history,
      // making its still-valid clips disappear from the dashboard.
      .is("progress->>kind", null)
      .order("created_at", { ascending: false }).limit(30),
    sb.from("jobs").select("finished_at, progress")
      .eq("user_id", user.id).eq("status", "done")
      .eq("progress->>kind", "clip_edit")
      .order("finished_at", { ascending: false }).limit(50),
  ]);

  const editedAt = new Map();
  for (const revision of revisions || []) {
    const clipId = revision.progress?.clip_id;
    if (clipId && !editedAt.has(clipId)) {
      editedAt.set(clipId, revision.finished_at);
    }
  }
  const withUrls = await Promise.all(
    (clips || []).map(async (c) => ({
      ...c,
      url: await signed(c.r2_key),
      editedAt: editedAt.get(c.id) || null,
    }))
  );
  // one section per stream batch, newest batch first, clips in 01/02/03 order
  const batches = (history || [])
    .filter((h) => h.status !== "failed")
    .map((h) => ({
      job: h,
      clips: withUrls
        .filter((c) => c.job_id === h.id)
        .sort((a, b) => {
          // A revision changes r2_key, so storage-key ordering made an edited
          // card jump from its old slot to the end. Pin recent work instead.
          if (a.editedAt || b.editedAt) {
            return new Date(b.editedAt || 0) - new Date(a.editedAt || 0);
          }
          return a.r2_key.localeCompare(b.r2_key);
        }),
    }))
    .filter((b) => b.clips.length > 0);
  const completedHistory = (history || []).filter(
    (job) => job.status === "done" || job.status === "failed"
  );

  return (
    <main className="max-w-6xl mx-auto px-6 py-10">
      <DashboardAutoRefresh />
      <WorkerStatusBanner />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-10">
        <div className="text-xl font-black">
          Stream<span className="text-[#9146FF]">Clip</span>
          <span className="ml-3 text-sm font-normal text-gray-400">
            {profile?.twitch_login}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:justify-end">
          <a href="/app/settings" className="text-sm font-bold text-gray-400 hover:text-white">
            Settings
          </a>
          <a href="/app/billing" className="text-sm font-bold text-gray-400 hover:text-white">
            Billing
          </a>
          <ClipCount initial={profile?.clips_per_stream} />
          <div className="text-sm font-bold px-4 py-2 rounded-full border border-[#2e2e4a] bg-[#15151f]">
            ⚡ {profile?.credits ?? 0} GW
          </div>
          <a href="/logout" className="text-xs font-bold text-gray-500 hover:text-white">
            Sign out
          </a>
        </div>
      </div>

      <ClipVod
        titleStrategy={profile?.style_profile?.title_strategy || "curiosity"}
        openingEffect={profile?.style_profile?.opening_effect || "punch_zoom"}
      />

      <TemplatePicker initial={profile?.style_profile} />

      <StylePicker initial={profile?.style_profile?.preset} />

      <ActiveJobs />

      {batches.length === 0 ? (
        <div className="text-center py-24 text-gray-400">
          <p className="text-2xl font-bold mb-2">No clips yet</p>
          <p>Choose your first template and run the latest finished VOD.</p>
          <a href="/app/onboarding"
            className="mt-5 inline-block rounded-xl bg-[#9146FF] px-5 py-3 font-black text-white">
            Start first batch
          </a>
        </div>
      ) : (
        batches.map(({ job, clips: batchClips }) => (
          <div key={job.id} className="mb-12">
            <div className="flex items-center gap-3 mb-3">
              <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wide">
                {new Date(job.finished_at || job.created_at).toLocaleDateString()}
                {" · "}
                <a href={job.vod_url} target="_blank" className="text-purple-300 hover:underline normal-case">
                  {job.vod_url.replace("https://www.", "")}
                </a>
              </h2>
              {job.progress?.preset && (
                <span className="text-[10px] font-black px-2 py-0.5 rounded-full border border-[#2e2e4a] text-gray-400 uppercase">
                  {job.progress.preset}
                </span>
              )}
              {job.progress?.title_strategy && (
                <span className="text-[10px] font-black px-2 py-0.5 rounded-full border border-[#2e2e4a] text-gray-400 uppercase">
                  {job.progress.title_strategy}
                </span>
              )}
              {job.progress?.opening_effect && (
                <span className="text-[10px] font-black px-2 py-0.5 rounded-full border border-[#2e2e4a] text-gray-400 uppercase">
                  {job.progress.opening_effect.replace("_", " ")}
                </span>
              )}
              {Number.isFinite(job.progress?.requested) && (
                <span className={`text-[10px] font-black px-2 py-0.5 rounded-full border uppercase ${
                  job.progress?.fulfilled
                    ? "border-green-900/70 text-green-400"
                    : "border-amber-900/70 text-amber-400"
                }`}>
                  {job.progress?.shipped ?? batchClips.length}/{job.progress.requested} shipped
                </span>
              )}
              {job.status === "running" && (
                <span className="text-[10px] font-black px-2 py-0.5 rounded-full border border-purple-800/70 bg-purple-950/30 text-purple-300 uppercase">
                  More clips loading
                </span>
              )}
            </div>
            {Number.isFinite(job.progress?.candidates) && (
              <p className="text-xs text-gray-500 mb-3">
                {job.progress.candidates} candidates · {job.progress.verified ?? 0} verified
                {" · "}{job.progress.rejected ?? 0} rejected
                {job.progress?.rejection_reasons?.length
                  ? ` · ${job.progress.rejection_reasons.join("; ")}`
                  : ""}
              </p>
            )}
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
              {batchClips.map((c) => (
                <div key={c.id}
                     className="rounded-2xl p-4 border border-[#23233a] bg-[#12121a]">
                  {c.editedAt && (
                    <div className="mb-2 flex items-center justify-between">
                      <span className="rounded-full border border-green-800/70 bg-green-950/30 px-2.5 py-1 text-[10px] font-black uppercase tracking-wide text-green-300">
                        Edited · latest version
                      </span>
                      <span className="text-[10px] text-gray-500">
                        {new Date(c.editedAt).toLocaleTimeString([], {
                          hour: "numeric", minute: "2-digit",
                        })}
                      </span>
                    </div>
                  )}
                  <ClipPlayer src={c.url} title={c.title} />
                  <ClipTimelineEditor clipId={c.id} />
                  <div className="flex items-start justify-between mt-3 gap-2">
                    <ClipEditor
                      clipId={c.id}
                      initialTitle={c.title}
                      initialHook={c.hook || ""}
                    />
                    <span className="shrink-0 text-xs font-black px-2 py-1 rounded-lg bg-[#9146FF]/20 text-purple-300">
                      {Number(c.score).toFixed(0)}/10
                    </span>
                  </div>
                  <a href={c.url} download
                     className="block text-center mt-3 bg-[#9146FF] hover:bg-[#7a2ff0] text-white text-sm font-bold py-2 rounded-lg">
                    Download
                  </a>
                  <ClipFeedback clipId={c.id} initial={c.feedback} />
                </div>
              ))}
              {job.status === "running" && Array.from({
                length: Math.max(
                  0,
                  Number(
                    job.progress?.requested ??
                    job.progress?.settings_snapshot?.clips_per_stream ?? 0
                  ) - batchClips.length
                ),
              }).map((_, index) => (
                <div key={`loading-${index}`}
                     className="rounded-2xl p-4 border border-[#23233a] bg-[#12121a]">
                  <div className="relative overflow-hidden rounded-xl w-full aspect-[9/16] bg-[#0a0a10]">
                    <div className="absolute inset-0 animate-pulse bg-gradient-to-b from-[#171725] via-[#222237] to-[#11111a]" />
                    <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
                      <span className="relative flex h-4 w-4 mb-4">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#9146FF] opacity-60" />
                        <span className="relative inline-flex rounded-full h-4 w-4 bg-[#9146FF]" />
                      </span>
                      <p className="text-sm font-bold text-white">Another clip is loading</p>
                      <p className="mt-1 text-xs text-gray-400">
                        Ready clips are usable now. This card will fill automatically.
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 h-4 w-3/4 rounded bg-[#222237] animate-pulse" />
                  <div className="mt-3 h-9 rounded-lg bg-[#1b1b2b] animate-pulse" />
                </div>
              ))}
            </div>
          </div>
        ))
      )}
      {completedHistory.length > 0 && (
        <div className="mt-14">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wide mb-3">
            Processed streams
          </h2>
          <div className="rounded-2xl border border-[#23233a] bg-[#12121a] divide-y divide-[#1c1c2e]">
            {completedHistory.map((h) => {
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
                    <RunAgain vodUrl={h.vod_url} />
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
