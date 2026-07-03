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
      </head>
      <body style={{ background: "#0a0a0f", color: "#e8e8f0" }}>
        {children}
      </body>
    </html>
  );
}
