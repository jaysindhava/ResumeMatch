export const API_URL =
  typeof window !== "undefined"
    ? "/api/backend"
    : process.env.BACKEND_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      process.env.PUBLIC_API_URL ||
      "http://52.66.224.136:8000";