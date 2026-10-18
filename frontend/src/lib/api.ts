const AWS_BACKEND_URL = "http://52.66.224.136:8000";
const rawUrl =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.PUBLIC_API_URL ||
  "";

const resolvedBackendUrl =
  rawUrl && !rawUrl.includes("onrender.com") && !rawUrl.includes("127.0.0.1")
    ? rawUrl
    : AWS_BACKEND_URL;

export const API_URL =
  typeof window !== "undefined" ? "/api/backend" : resolvedBackendUrl;