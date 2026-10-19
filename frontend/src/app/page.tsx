"use client";

import { API_URL } from "@/lib/api";
import { getSessionId } from "@/lib/session";
import { useState, useEffect } from "react";

export default function DashboardPage() {
  const [resumeStatus, setResumeStatus] = useState<"checking" | "none" | "loaded">("checking");
  const [resumeInfo, setResumeInfo] = useState<{ filename?: string; candidate_years?: number } | null>(null);

  useEffect(() => {
    const sessionId = getSessionId();
    fetch(`${API_URL}/resume-status?session_id=${encodeURIComponent(sessionId)}`)
      .then((res) => res.json())
      .then((data) => {
        if (data && data.has_resume) {
          setResumeStatus("loaded");
          setResumeInfo({ filename: data.filename, candidate_years: data.candidate_years });
        } else {
          setResumeStatus("none");
        }
      })
      .catch(() => setResumeStatus("none"));
  }, []);

  return (
    <div className="space-y-12">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest mb-3" style={{ color: "var(--accept)" }}>
          ● case file — active session
        </p>
        <h1 className="font-display text-4xl font-bold leading-tight">
          One resume, marked up<br />against real openings.
        </h1>
        <p className="mt-4 max-w-lg" style={{ color: "var(--muted)" }}>
          Upload once. Every job you review gets read against it line by line —
          what matches, what&apos;s missing, and what can honestly be reworded.
        </p>
      </div>

      <div className="rounded-lg p-4 flex items-center justify-between" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <div className="flex items-center gap-3">
          <span className="w-2 h-2 rounded-full" style={{ background: resumeStatus === "loaded" ? "var(--accept)" : "var(--flag)", boxShadow: `0 0 8px ${resumeStatus === "loaded" ? "var(--accept)" : "var(--flag)"}` }} />
          <span className="font-mono text-xs uppercase tracking-wider">
            {resumeStatus === "checking" && "Checking device session..."}
            {resumeStatus === "loaded" && `Resume active — ${resumeInfo?.candidate_years !== undefined ? `~${resumeInfo.candidate_years} yrs exp detected` : "ready for analysis"}`}
            {resumeStatus === "none" && "No resume loaded yet on this device"}
          </span>
        </div>
        <a href="/upload" className="font-mono text-xs hover:underline" style={{ color: "var(--accent)" }}>
          {resumeStatus === "loaded" ? "Replace →" : "Upload resume →"}
        </a>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { n: "01", href: "/upload", title: "Upload", desc: "Parse and embed your resume.", c: "var(--accept)" },
          { n: "02", href: "/jobs", title: "Find jobs", desc: "Search live postings, rank by fit.", c: "var(--accent)" },
          { n: "03", href: "/history", title: "History", desc: "Past searches and applications.", c: "var(--flag)" },
        ].map((item) => (
          <a key={item.n} href={item.href} className="glow-btn rounded-lg p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)", ["--glow-color" as string]: item.c }}>
            <span className="font-mono text-xs" style={{ color: item.c }}>{item.n}</span>
            <h2 className="font-display text-lg font-semibold mt-2">{item.title}</h2>
            <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>{item.desc}</p>
          </a>
        ))}
      </div>
    </div>
  );
}