export default function sitemap() {
  const base = process.env.NEXT_PUBLIC_SITE_URL || "https://streamclip.app";
  return [
    "", "/pricing", "/faq", "/demo", "/changelog", "/status",
    "/legal/terms", "/legal/privacy", "/legal/cookies",
  ].map((path) => ({
    url: `${base}${path}`,
    lastModified: new Date(),
    changeFrequency: path === "/changelog" ? "weekly" : "monthly",
    priority: path === "" ? 1 : 0.6,
  }));
}
