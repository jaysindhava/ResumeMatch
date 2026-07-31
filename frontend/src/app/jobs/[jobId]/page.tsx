"use client";

import { API_URL } from "@/lib/api";
import { useState, useEffect } from "react";

interface Job { job_id: string; title: string; company: string; location: string; description: string; }
interface AnalysisResult {
  matched_skills: string[]; missing_skills: string[];
  safe_rewrites: { chunk_id: string; requirement: string; original: string; rewritten: string }[];
  flagged_for_review: { chunk_id: string; requirement: string; original: string; rewritten: string; reason: string[] }[];
}

export default function JobDetailPage() {
  const [job, setJob] = useState<Job | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const stored = localStorage.getItem("selectedJob");
    if (stored) setJob(JSON.parse(stored));
  }, []);

  const handleAnalyze = async () => {
    if (!job) return;
    setLoading(true); setError("");
    try {
      const response = await fetch(`${API_URL}/analyze`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_description: job.description }),
      });
      const data = await response.json();
      if (response.ok) setAnalysis(data); else setError(data.detail || "Analysis failed");
    } catch { setError("Could not reach the backend."); }
    finally { setLoading(false); }
  };

  if (!job) return <p style={{ color: "var(--muted)" }}>No job selected. Go back to Find jobs.</p>;

  return (
    <div className="space-y-8">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>Step 03 — redlined</p>
        <h1 className="font-display text-3xl font-bold">{job.title}</h1>
        <p style={{ color: "var(--muted)" }}>{job.company} — {job.location}</p>
      </div>

      <button onClick={handleAnalyze} disabled={loading}
        className="glow-btn px-5 py-2.5 rounded-md font-mono text-xs uppercase tracking-wider disabled:opacity-40"
        style={{ background: "var(--accept)", color: "#062412", ["--glow-color" as string]: "var(--accept)" }}>
        {loading ? "Reading against resume..." : "Run gap analysis"}
      </button>
      {error && <p className="text-sm font-mono" style={{ color: "var(--flag)" }}>{error}</p>}

      {analysis && (
        <div className="space-y-10">
          <div className="rounded-lg p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <p className="font-mono text-xs uppercase tracking-widest mb-4" style={{ color: "var(--muted)" }}>Margin notes</p>
            <div className="flex flex-wrap gap-x-1 gap-y-3 leading-loose">
              {analysis.matched_skills.map((s) => (
                <span key={s} className="mr-3 px-2 py-0.5 rounded" style={{ background: "rgba(57,255,136,0.1)", color: "var(--accept)" }}>{s}</span>
              ))}
              {analysis.missing_skills.map((s) => (
                <span key={s} className="mr-3 px-2 py-0.5 rounded" style={{ background: "rgba(255,92,92,0.1)", color: "var(--flag)" }}>[{s} — not found]</span>
              ))}
            </div>
          </div>

          {analysis.safe_rewrites.length > 0 && (
            <div>
              <p className="font-mono text-xs uppercase tracking-widest mb-3" style={{ color: "var(--accept)" }}>✓ Safe rewrites</p>
              {analysis.safe_rewrites.map((r, i) => (
                <div key={i} className="text-sm py-3 border-t" style={{ borderColor: "var(--border)" }}>
                  <p style={{ color: "var(--muted)" }} className="line-through">{r.original}</p>
                  <p className="mt-1" style={{ color: "var(--accept)" }}>{r.rewritten}</p>
                </div>
              ))}
            </div>
          )}

          {analysis.flagged_for_review.length > 0 && (
            <div>
              <p className="font-mono text-xs uppercase tracking-widest mb-1" style={{ color: "var(--flag)" }}>✕ Rejected — would fabricate a claim</p>
              {analysis.flagged_for_review.map((r, i) => (
                <div key={i} className="text-sm py-3 border-t" style={{ borderColor: "var(--border)" }}>
                  <p style={{ color: "var(--muted)" }}>{r.original}</p>
                  <p className="mt-1 line-through" style={{ color: "var(--flag)" }}>{r.rewritten}</p>
                  <p className="text-xs mt-1 font-mono" style={{ color: "var(--muted)" }}>reason: {r.reason.join(", ")}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}