import type { NextConfig } from "next";

const AWS_BACKEND_URL = "http://13.235.133.173:8000";

const rawUrl =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.PUBLIC_API_URL ||
  "";

const BACKEND_URL =
  rawUrl && !rawUrl.includes("onrender.com") && !rawUrl.includes("127.0.0.1")
    ? rawUrl
    : AWS_BACKEND_URL;

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
