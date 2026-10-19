"use client";

import { useState, useEffect } from "react";
import { API_URL } from "@/lib/api";
import { getSessionId } from "@/lib/session";

interface Application { id: number; job_title: string; company: string; tailored_resume_summary: string; status: string; created_at: string; }
interface ViewedJob { id: number; job_id: string; job_title: string; company: string; created_at: string; }
interface SearchRecord { id: number; search_title: string; search_location: string; results_count: number; created_at: string; viewed_jobs: ViewedJob[]; }

export default function HistoryPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [searches, setSearches] = useState<SearchRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const sessionId = getSessionId();
    Promise.all([
      fetch(`${API_URL}/history?session_id=${encodeURIComponent(sessionId)}`).then((r) => r.json()),
      fetch(`${API_URL}/search-history-detailed?session_id=${encodeURIComponent(sessionId)}`).then((r) => r.json()),
    ]).then(([a, s]) => {
      setApplications(a?.history || []);
      setSearches(s?.history || []);
    })
      .catch(() => {}).finally(() => setLoading(false));
  }, []);

  const fmt = (iso: string) => new Date(iso).toLocaleString();

  return (
    <div className="space-y-12">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>Record</p>
        <h1 className="font-display text-3xl font-bold">History</h1>
      </div>

      {loading && <p style={{ color: "var(--muted)" }}>Loading...</p>}

      {!loading && (
        <>
          <section>
            <h2 className="font-display text-xl font-semibold mb-4">Applications</h2>
            {applications.length === 0 && <p className="text-sm" style={{ color: "var(--muted)" }}>None yet — apply to a job from its analysis page.</p>}
            <div className="space-y-2">
              {applications.map((a) => (
                <div key={a.id} className="rounded-lg p-4 flex justify-between items-start" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                  <div>
                    <h3 className="font-semibold">{a.job_title} — {a.company}</h3>
                    <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>{a.tailored_resume_summary}</p>
                    <p className="font-mono text-xs mt-1" style={{ color: "var(--muted)" }}>{fmt(a.created_at)}</p>
                  </div>
                  <span className="font-mono text-xs uppercase px-2 py-1 rounded" style={{ border: "1px solid var(--border)", color: "var(--accept)" }}>{a.status}</span>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h2 className="font-display text-xl font-semibold mb-4">Searches</h2>
            {searches.length === 0 && <p className="text-sm" style={{ color: "var(--muted)" }}>None yet.</p>}
            <div className="space-y-3">
              {searches.map((s) => (
                <div key={s.id} className="rounded-lg p-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                  <div className="flex justify-between items-center">
                    <div>
                      <span className="text-sm">{s.search_title} in {s.search_location || "any location"}</span>
                      <span className="font-mono text-xs ml-2" style={{ color: "var(--muted)" }}>{fmt(s.created_at)}</span>
                    </div>
                    <span className="font-mono text-xs" style={{ color: "var(--accent)" }}>{s.results_count} results</span>
                  </div>

                  {s.viewed_jobs.length > 0 && (
                    <div className="mt-3 pl-4 border-l" style={{ borderColor: "var(--border)" }}>
                      <p className="font-mono text-xs uppercase tracking-wider mb-2" style={{ color: "var(--muted)" }}>Jobs viewed from this search</p>
                      {s.viewed_jobs.map((v) => (
                        <p key={v.id} className="text-sm py-1" style={{ color: "var(--text)" }}>
                          {v.job_title} — <span style={{ color: "var(--muted)" }}>{v.company}</span>
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}