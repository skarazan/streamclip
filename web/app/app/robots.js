export default function robots() {
  const base = process.env.NEXT_PUBLIC_SITE_URL || "https://streamclip.app";
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/app/", "/dashboard", "/api/"] }],
    sitemap: `${base}/sitemap.xml`,
  };
}
