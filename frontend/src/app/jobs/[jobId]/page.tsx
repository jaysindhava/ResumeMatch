"use client";

import { useState, useEffect } from "react";
import { API_URL } from "@/lib/api";

interface Job { job_id: string; title: string; company: string; location: string; description: string; }
interface Rewrite { chunk_id: string; requirement: string; original: string; rewritten: string; }
interface AnalysisResult {
  matched_skills: string[]; missing_skills: string[];
  safe_rewrites: Rewrite[];
  flagged_for_review: { chunk_id: string; requirement: string; original: string; rewritten: string; reason: string[] }[];
}

export default function JobDetailPage() {
  const [job, setJob] = useState<Job | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [applied, setApplied] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("selectedJob");
    const searchId = localStorage.getItem("currentSearchId");
    if (stored) {
      const j = JSON.parse(stored);
      setJob(j);
      if (searchId) {
        fetch(`${API_URL}/log-job-view`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ search_id: parseInt(searchId), job_id: j.job_id, job_title: j.title, company: j.company }),
        }).catch(() => {});
      }
    }
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

  const handleApply = async () => {
    if (!job) return;
    try {
      await fetch(`${API_URL}/apply-job`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: job.job_id, job_title: job.title, company: job.company,
          safe_rewrites: analysis?.safe_rewrites || [],
        }),
      });
      setApplied(true);
    } catch {
      setError("Could not log application.");
    }
  };

  const handleDownloadChanges = () => {
    if (!job || !analysis) return;
    const lines: string[] = [];
    lines.push(`Resume changes for: ${job.title} at ${job.company}`);
    lines.push(`Generated: ${new Date().toLocaleString()}`);
    lines.push("");
    lines.push("=== MATCHED SKILLS ===");
    lines.push(analysis.matched_skills.join(", ") || "none");
    lines.push("");
    lines.push("=== MISSING SKILLS ===");
    lines.push(analysis.missing_skills.join(", ") || "none");
    lines.push("");
    lines.push("=== SUGGESTED REWRITES (applied) ===");
    if (analysis.safe_rewrites.length === 0) {
      lines.push("No safe rewrites were found - original resume text used as-is.");
    } else {
      analysis.safe_rewrites.forEach((r, i) => {
        lines.push(`${i + 1}. For requirement: ${r.requirement}`);
        lines.push(`   Original:  ${r.original}`);
        lines.push(`   Rewritten: ${r.rewritten}`);
        lines.push("");
      });
    }
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `resume-changes-${job.company.replace(/\s+/g, "_")}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!job) return <p style={{ color: "var(--muted)" }}>No job selected. Go back to Find jobs.</p>;

  return (
    <div className="space-y-8">
      <a href="/jobs" className="font-mono text-xs" style={{ color: "var(--muted)" }}>← Back to search results</a>

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

          <div className="flex gap-3 pt-4 border-t" style={{ borderColor: "var(--border)" }}>
            <button onClick={handleDownloadChanges}
              className="px-4 py-2 rounded-md font-mono text-xs uppercase tracking-wider"
              style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}>
              Download changes (.txt)
            </button>
            <button onClick={handleApply} disabled={applied}
              className="glow-btn px-4 py-2 rounded-md font-mono text-xs uppercase tracking-wider disabled:opacity-40"
              style={{ background: "var(--accent)", color: "#2b1a00", ["--glow-color" as string]: "var(--accent)" }}>
              {applied ? "✓ Applied" : "Mark as applied"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}