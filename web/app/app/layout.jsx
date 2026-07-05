import Script from "next/script";

export const metadata = {
  title: "StreamClip — your stream, clipped while you sleep",
  description: "Automatic scored, styled Shorts from your Twitch VODs.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <Script src="https://cdn.tailwindcss.com" strategy="beforeInteractive" />
        {/* fonts used by caption-style previews only; worker bundles its own TTFs */}
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Anton&family=Montserrat:wght@800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body style={{ background: "#0a0a0f", color: "#e8e8f0" }}>
        {children}
      </body>
    </html>
  );
}
