"use client";

import { API_URL } from "@/lib/api";
import { useState } from "react";
import { useRouter } from "next/navigation";

interface Job { job_id: string; title: string; company: string; location: string; description: string; url: string; posted_date: string; }
interface RankedJob { job_id: string; title: string; company: string; location: string; url: string; final_score: number; skill_overlap: number; seniority_match: number; matched_skills: string[]; missing_skills: string[]; }

export default function JobsPage() {
  const [title, setTitle] = useState("python developer");
  const [location, setLocation] = useState("Pune");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [rankings, setRankings] = useState<RankedJob[]>([]);
  const [rankingsLoading, setRankingsLoading] = useState(false);
  const router = useRouter();

  const handleSearch = async () => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ title, location, results: "10" });
      const response = await fetch(`${API_URL}/search-jobs?${params}`);
      const data = await response.json();
      if (response.ok) setJobs(data.jobs); else setError(data.detail || "Search failed");
    } catch { setError("Could not reach the backend."); }
    finally { setLoading(false); }
  };

  const handleAnalyze = (job: Job) => {
    localStorage.setItem("selectedJob", JSON.stringify(job));
    router.push(`/jobs/${job.job_id}`);
  };

  const handleGetRankings = async () => {
    setRankingsLoading(true);
    try {
      const response = await fetch(`${API_URL}/rankings?top_n=8`);
      const data = await response.json();
      if (response.ok) setRankings(data.rankings);
    } catch {} finally { setRankingsLoading(false); }
  };

  return (
    <div className="space-y-10">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>Step 02</p>
        <h1 className="font-display text-3xl font-bold">Find jobs</h1>
      </div>

      <div className="flex gap-2">
        <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Job title"
          className="flex-1 px-4 py-3 text-sm rounded-md outline-none" style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
        <input type="text" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location"
          className="flex-1 px-4 py-3 text-sm rounded-md outline-none" style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
        <button onClick={handleSearch} disabled={loading}
          className="glow-btn px-6 rounded-md font-mono text-xs uppercase tracking-wider disabled:opacity-40"
          style={{ background: "var(--accent)", color: "#2b1a00", ["--glow-color" as string]: "var(--accent)" }}>
          {loading ? "..." : "Search"}
        </button>
      </div>
      {error && <p className="text-sm font-mono" style={{ color: "var(--flag)" }}>{error}</p>}

      <div className="space-y-2">
        {jobs.map((job) => (
          <div key={job.job_id} className="rounded-lg p-4 flex justify-between items-start gap-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <div>
              <h3 className="font-display font-semibold">{job.title}</h3>
              <p className="text-sm" style={{ color: "var(--muted)" }}>{job.company} — {job.location}</p>
              <p className="text-sm mt-1 line-clamp-1" style={{ color: "var(--muted)" }}>{job.description}</p>
            </div>
            <button onClick={() => handleAnalyze(job)} className="font-mono text-xs uppercase tracking-wider whitespace-nowrap" style={{ color: "var(--accept)" }}>
              Analyze →
            </button>
          </div>
        ))}
      </div>

      <div className="pt-8 border-t" style={{ borderColor: "var(--border)" }}>
        <div className="flex items-center justify-between mb-6">
          <h2 className="font-display text-2xl font-bold">Ranked matches</h2>
          <button onClick={handleGetRankings} disabled={rankingsLoading}
            className="glow-btn px-4 py-2 rounded-md font-mono text-xs uppercase tracking-wider disabled:opacity-40"
            style={{ background: "var(--accept)", color: "#062412", ["--glow-color" as string]: "var(--accept)" }}>
            {rankingsLoading ? "Scoring..." : "Get top matches"}
          </button>
        </div>
        <div className="space-y-2">
          {rankings.map((job, i) => (
            <div key={job.job_id} className="rounded-lg p-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="flex justify-between items-baseline">
                <div>
                  <span className="font-mono text-xs" style={{ color: "var(--muted)" }}>{String(i + 1).padStart(2, "0")}</span>
                  <span className="font-display font-semibold ml-2">{job.title}</span>
                  <span className="text-sm ml-2" style={{ color: "var(--muted)" }}>{job.company}</span>
                </div>
                <span className="font-mono text-sm font-semibold" style={{ color: "var(--accent)" }}>{Math.round(job.final_score * 100)}%</span>
              </div>
              <p className="text-sm mt-1">
                <span style={{ color: "var(--accept)" }}>{job.matched_skills.join(", ") || "—"}</span>
                {job.missing_skills.length > 0 && <span style={{ color: "var(--flag)" }}> · missing: {job.missing_skills.join(", ")}</span>}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}