import type { NextConfig } from "next";

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.PUBLIC_API_URL ||
  "http://52.66.224.136:8000";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: BACKEND_URL,
  },
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },
};



export default nextConfig;
