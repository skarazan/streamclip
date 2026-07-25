import "./globals.css";
import Script from "next/script";

export const metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL || "https://streamclip.app"
  ),
  title: "StreamClip — your stream, clipped while you sleep",
  description: "Automatic scored, styled Shorts from your Twitch VODs.",
  openGraph: {
    title: "StreamClip — your stream, clipped while you sleep",
    description: "Arc-verified vertical Shorts from your Twitch VODs.",
    type: "website",
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        {/* fonts used by caption-style previews only; worker bundles its own TTFs */}
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Anton&family=Montserrat:wght@800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        {children}
        {process.env.NEXT_PUBLIC_PLAUSIBLE_DOMAIN && (
          <Script
            defer
            data-domain={process.env.NEXT_PUBLIC_PLAUSIBLE_DOMAIN}
            src="https://plausible.io/js/script.js"
            strategy="afterInteractive"
          />
        )}
      </body>
    </html>
  );
}
