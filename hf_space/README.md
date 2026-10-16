---
title: ResumeMatch Backend
emoji: 🎯
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# ResumeMatch Backend API

FastAPI backend for the ResumeMatch AI-powered resume tailoring application.

## Endpoints

- `GET /` — Health check
- `POST /upload-resume` — Upload and embed a PDF resume
- `GET /search-jobs` — Search live job postings
- `POST /analyze` — Analyze a job description against your resume
- `POST /rank-searched-jobs` — Rank jobs by resume fit
- `GET /history` — Application history
