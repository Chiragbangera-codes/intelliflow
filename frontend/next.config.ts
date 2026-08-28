import type { NextConfig } from "next";

/**
 * Next.js configuration for IntelliFlow AI.
 *
 * - `output: "standalone"` produces a minimal production build suitable for Docker.
 * - `reactStrictMode: true` highlights potential issues during development.
 * - Public env vars prefixed NEXT_PUBLIC_ are baked into the client bundle at build time.
 */
const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,

  // Expose backend API URL to client-side code
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1",
    NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME ?? "IntelliFlow AI",
  },

  // Disable the X-Powered-By header for security
  poweredByHeader: false,
};

export default nextConfig;
