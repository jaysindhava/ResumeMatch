import type { NextConfig } from "next";

const AWS_BACKEND_URL = "http://13.207.165.26:8000";

const rawUrl =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.PUBLIC_API_URL ||
  "";

const BACKEND_URL =
  rawUrl &&
  !rawUrl.includes("onrender.com") &&
  !rawUrl.includes("127.0.0.1") &&
  !rawUrl.includes("52.66.224.136") &&
  !rawUrl.includes("13.235.133.173") &&
  !rawUrl.includes("16.4.45.221") &&
  !rawUrl.includes("13.232.110.249") &&
  !rawUrl.includes("3.109.220.205")
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
