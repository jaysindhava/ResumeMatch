export function getSessionId(): string {
  if (typeof window === "undefined") return "default";
  let id = localStorage.getItem("resumematch_session_id");
  if (!id) {
    id = "sess_" + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
    localStorage.setItem("resumematch_session_id", id);
  }
  return id;
}
