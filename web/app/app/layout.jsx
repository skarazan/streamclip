import "./globals.css";

export const metadata = {
  title: "StreamClip — your stream, clipped while you sleep",
  description: "Automatic scored, styled Shorts from your Twitch VODs.",
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
      <body>{children}</body>
    </html>
  );
}
