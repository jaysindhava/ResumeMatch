"use client";

import { API_URL } from "@/lib/api";
import { getSessionId } from "@/lib/session";
import { useState } from "react";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleUpload = async () => {
    if (!file) return;
    setStatus("uploading");
    const formData = new FormData();
    formData.append("file", file);
    formData.append("session_id", getSessionId());
    try {
      const response = await fetch(`${API_URL}/upload-resume`, { method: "POST", body: formData });
      const data = await response.json();
      if (response.ok) {
        setStatus("success");
        const expStr = data.candidate_years !== undefined ? ` (detected ~${data.candidate_years} yrs exp)` : "";
        setMessage(`${data.chunks_created} chunks parsed and indexed for this device${expStr}.`);
      } else {
        setStatus("error");
        setMessage(data.detail || "Upload failed");
      }
    } catch {
      setStatus("error");
      setMessage("Could not reach the backend.");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>Step 01</p>
        <h1 className="font-display text-3xl font-bold">Upload your resume</h1>
        <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>PDF only. Replaces any resume currently active.</p>
      </div>

      <div className="rounded-lg" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <label className="block p-10 text-center cursor-pointer hover:bg-white/5 transition rounded-t-lg">
          <input type="file" accept=".pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} className="hidden" />
          <span className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--muted)" }}>
            {file ? file.name : "Click to choose a PDF"}
          </span>
        </label>
        {file && (
          <div className="border-t px-6 py-4 flex items-center justify-between" style={{ borderColor: "var(--border)" }}>
            <span className="font-mono text-xs" style={{ color: "var(--muted)" }}>{file.name}</span>
            <button
              onClick={handleUpload}
              disabled={status === "uploading"}
              className="glow-btn px-4 py-2 rounded-md text-sm font-mono uppercase tracking-wider disabled:opacity-40"
              style={{ background: "var(--accept)", color: "#062412", ["--glow-color" as string]: "var(--accept)" }}
            >
              {status === "uploading" ? "Parsing..." : "Upload"}
            </button>
          </div>
        )}
      </div>

      {status === "success" && <p className="text-sm font-mono" style={{ color: "var(--accept)" }}>✓ {message}</p>}
      {status === "error" && <p className="text-sm font-mono" style={{ color: "var(--flag)" }}>✕ {message}</p>}
    </div>
  );
}