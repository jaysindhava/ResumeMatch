import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ||
      process.env.PUBLIC_API_URL ||
      "http://52.66.224.136:8000",
  },
};


export default nextConfig;
