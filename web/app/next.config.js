/** @type {import('next').NextConfig} */
const nextConfig = {
  // Keep production validation builds away from the live dev server. Sharing
  // `.next` replaces the dev CSS manifest underneath the running process.
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
};

module.exports = nextConfig;
