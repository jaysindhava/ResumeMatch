"use client";

import { useState, useEffect } from "react";
import { API_URL } from "@/lib/api";
import { getSessionId } from "@/lib/session";

interface Job { job_id: string; title: string; company: string; location: string; description: string; }
interface Rewrite { chunk_id: string; requirement: string; original: string; rewritten: string; }
interface ExperienceAnalysis {
  job_years_required: number;
  candidate_years: number;
  status: string;
  is_match: boolean;
  candidate_summary: string;
  comparison_text: string;
}
interface AnalysisResult {
  matched_skills: string[];
  missing_skills: string[];
  safe_rewrites: Rewrite[];
  flagged_for_review: { chunk_id: string; requirement: string; original: string; rewritten: string; reason: string[] }[];
  min_years_experience?: number;
  experience_analysis?: ExperienceAnalysis;
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
        const sessionId = getSessionId();
        fetch(`${API_URL}/log-job-view`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ search_id: parseInt(searchId), job_id: j.job_id, job_title: j.title, company: j.company, session_id: sessionId }),
        }).catch(() => {});
      }
    }
  }, []);

  const handleAnalyze = async () => {
    if (!job) return;
    setLoading(true); setError("");
    try {
      const sessionId = getSessionId();
      const response = await fetch(`${API_URL}/analyze`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_description: job.description, session_id: sessionId }),
      });
      const data = await response.json();
      if (response.ok) {
        setAnalysis(data);
      } else {
        setError(data.detail || "Analysis failed");
      }
    } catch { setError("Could not reach the backend."); }
    finally { setLoading(false); }
  };

  const handleApply = async () => {
    if (!job) return;
    try {
      const sessionId = getSessionId();
      await fetch(`${API_URL}/apply-job`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: job.job_id, job_title: job.title, company: job.company,
          safe_rewrites: analysis?.safe_rewrites || [],
          session_id: sessionId,
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
    if (analysis.experience_analysis) {
      lines.push("=== YEARS OF EXPERIENCE COMPARISON ===");
      lines.push(`Job Requirement:    ${analysis.experience_analysis.job_years_required > 0 ? `${analysis.experience_analysis.job_years_required}+ years` : "Entry-level / Not specified"}`);
      lines.push(`Resume Detected:    ~${analysis.experience_analysis.candidate_years} years (${analysis.experience_analysis.candidate_summary})`);
      lines.push(`Match Status:       ${analysis.experience_analysis.status}`);
      lines.push(`Assessment:         ${analysis.experience_analysis.comparison_text}`);
      lines.push("");
    }
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
      <a href="/jobs" className="font-mono text-xs hover:underline" style={{ color: "var(--muted)" }}>← Back to search results</a>

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
      {error && (
        <div className="p-3 rounded-md border" style={{ borderColor: "rgba(255,92,92,0.3)", background: "rgba(255,92,92,0.06)" }}>
          <p className="text-sm font-mono" style={{ color: "var(--flag)" }}>✕ {error}</p>
          {error.includes("upload") && (
            <a href="/upload" className="font-mono text-xs mt-2 inline-block underline" style={{ color: "var(--accent)" }}>
              Go to Upload Resume →
            </a>
          )}
        </div>
      )}

      {analysis && (
        <div className="space-y-10">
          {analysis.experience_analysis && (
            <div className="rounded-lg p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="flex items-center justify-between mb-4">
                <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
                  Years of Experience Comparison
                </span>
                <span
                  className="font-mono text-xs uppercase px-2.5 py-1 rounded font-semibold tracking-wider flex items-center gap-1.5"
                  style={{
                    background: analysis.experience_analysis.is_match ? "rgba(57,255,136,0.12)" : "rgba(255,92,92,0.12)",
                    color: analysis.experience_analysis.is_match ? "var(--accept)" : "var(--flag)",
                    border: `1px solid ${analysis.experience_analysis.is_match ? "rgba(57,255,136,0.3)" : "rgba(255,92,92,0.3)"}`,
                  }}
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: analysis.experience_analysis.is_match ? "var(--accept)" : "var(--flag)" }} />
                  {analysis.experience_analysis.status}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div className="p-3 rounded-md" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)" }}>
                  <p className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--muted)" }}>Job Requirement</p>
                  <p className="font-display text-xl font-bold mt-1">
                    {analysis.experience_analysis.job_years_required > 0
                      ? `${analysis.experience_analysis.job_years_required}+ Years`
                      : "Fresher / Entry-Level"}
                  </p>
                  <p className="font-mono text-xs mt-1" style={{ color: "var(--muted)" }}>
                    {analysis.experience_analysis.job_years_required > 0 ? "Minimum required" : "No min yrs specified"}
                  </p>
                </div>

                <div className="p-3 rounded-md" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)" }}>
                  <p className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--muted)" }}>Resume Experience</p>
                  <p className="font-display text-xl font-bold mt-1" style={{ color: "var(--accent)" }}>
                    ~{analysis.experience_analysis.candidate_years} Years
                  </p>
                  <p className="font-mono text-xs mt-1 truncate" style={{ color: "var(--muted)" }} title={analysis.experience_analysis.candidate_summary}>
                    {analysis.experience_analysis.candidate_summary || "Calculated from resume"}
                  </p>
                </div>

                <div className="p-3 rounded-md" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)" }}>
                  <p className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--muted)" }}>Experience Delta</p>
                  <p className="font-display text-xl font-bold mt-1" style={{ color: analysis.experience_analysis.is_match ? "var(--accept)" : "var(--flag)" }}>
                    {analysis.experience_analysis.job_years_required <= 0
                      ? "✓ Qualified"
                      : analysis.experience_analysis.candidate_years >= analysis.experience_analysis.job_years_required
                        ? `+${(analysis.experience_analysis.candidate_years - analysis.experience_analysis.job_years_required).toFixed(1)} yr surplus`
                        : `-${(analysis.experience_analysis.job_years_required - analysis.experience_analysis.candidate_years).toFixed(1)} yr gap`}
                  </p>
                  <p className="font-mono text-xs mt-1" style={{ color: "var(--muted)" }}>
                    {analysis.experience_analysis.is_match ? "Meets or exceeds criteria" : "Needs project highlight"}
                  </p>
                </div>
              </div>

              <div className="p-3.5 rounded-md text-xs leading-relaxed" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border)", color: "var(--text)" }}>
                <p className="font-mono text-[10px] uppercase tracking-wider mb-1" style={{ color: "var(--muted)" }}>Assessment & Strategy</p>
                <p>{analysis.experience_analysis.comparison_text}</p>
              </div>
            </div>
          )}

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