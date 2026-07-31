import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ResumeMatch",
  description: "AI-powered resume tailoring and job matching",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen">
        <header className="border-b sticky top-0 z-10" style={{ borderColor: "var(--border)", background: "rgba(11,12,14,0.85)", backdropFilter: "blur(8px)" }}>
          <div className="max-w-3xl mx-auto px-6 pt-6 pb-4">
            <div className="flex items-baseline justify-between">
              <h1 className="font-display text-xl font-bold tracking-tight">
                Resume<span style={{ color: "var(--accept)" }}>Match</span>
              </h1>
              <span className="font-mono text-xs" style={{ color: "var(--muted)" }}>engine online</span>
            </div>
            <nav className="flex gap-6 mt-4 font-mono text-xs uppercase tracking-wider">
              <a href="/" className="hover:text-white transition" style={{ color: "var(--muted)" }}>Dashboard</a>
              <a href="/upload" className="hover:text-white transition" style={{ color: "var(--muted)" }}>Upload</a>
              <a href="/jobs" className="hover:text-white transition" style={{ color: "var(--muted)" }}>Find jobs</a>
              <a href="/history" className="hover:text-white transition" style={{ color: "var(--muted)" }}>History</a>
            </nav>
          </div>
        </header>
        <main className="max-w-3xl mx-auto px-6 py-10">{children}</main>
      </body>
    </html>
  );
}