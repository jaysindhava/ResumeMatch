import sys
import os
import json
import traceback
from typing import List
import io

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil

# ── S3 support (used in production; falls back to local disk in dev) ──────────
try:
    import boto3
    from botocore.exceptions import NoCredentialsError, ClientError
    _s3_client = boto3.client("s3")
    S3_BUCKET = os.getenv("S3_BUCKET", "")
    USE_S3 = bool(S3_BUCKET)
except ImportError:
    _s3_client = None
    S3_BUCKET = ""
    USE_S3 = False


def _save_resume(file: UploadFile, local_path: str) -> None:
    """Save the uploaded resume either to S3 (production) or local disk (dev)."""
    if USE_S3 and _s3_client:
        file.file.seek(0)
        _s3_client.upload_fileobj(file.file, S3_BUCKET, f"resumes/{file.filename}")
    else:
        file.file.seek(0)
        with open(local_path, "wb") as f:
            shutil.copyfileobj(file.file, f)


def _download_resume_for_parsing(file: UploadFile, local_path: str) -> str:
    """Ensure a local copy of the resume exists for the PDF parser, returns path."""
    if USE_S3 and _s3_client:
        # Download from S3 to a temp local path so the parser can read it
        _s3_client.download_file(S3_BUCKET, f"resumes/{file.filename}", local_path)
    return local_path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp import ClientSession as ATSClientSession, StdioServerParameters as ATSServerParameters
from mcp.client.stdio import stdio_client as ats_stdio_client

from app.parsers.resume_parser import (
    extract_raw_text, split_into_sections, chunk_bullets,
    chunk_skills, chunk_education, chunk_certifications,
)
from app.vectorstore.setup import get_resume_collection, embed_and_store
from app.agents.ranking import extract_job_requirements_async, rank_all_jobs_async, rank_job_list_async
from app.agents.tailoring_graph import tailoring_app

app = FastAPI(title="ResumeMatch API")

# CORS: always allow localhost for dev; add production Vercel URL via env var
_cors_origins = ["http://localhost:3000"]
_frontend_url = os.getenv("FRONTEND_URL", "").strip()
if _frontend_url:
    _cors_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "data/resumes"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ATS_SERVER_PARAMS = ATSServerParameters(command="python", args=["app/mcp_servers/ats_tracker_server.py"])
JOB_SEARCH_SERVER_PARAMS = StdioServerParameters(command="python", args=["app/mcp_servers/job_search_server.py"])


@app.get("/")
def health_check():
    """Simple health check - confirms the server is running."""
    return {"status": "ok", "message": "ResumeMatch API is running"}


@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """Accepts a PDF resume upload, saves it, and runs it through the full
    Phase 1-2 pipeline: parse -> chunk -> embed -> store in Chroma."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    save_path = os.path.join(UPLOAD_DIR, file.filename)
    _save_resume(file, save_path)
    local_path = _download_resume_for_parsing(file, save_path)

    try:
        text = extract_raw_text(local_path)
        sections = split_into_sections(text)

        all_chunks = []
        all_chunks += chunk_bullets(sections.get("professional_experience", ""), "professional_experience")
        all_chunks += chunk_bullets(sections.get("projects", ""), "projects")
        all_chunks += chunk_skills(sections.get("skills", ""))
        all_chunks += chunk_education(sections.get("education", ""))
        all_chunks += chunk_certifications(sections.get("certifications", ""))

        collection = get_resume_collection()
        embed_and_store(all_chunks, collection)

        return {"status": "success", "filename": file.filename, "chunks_created": len(all_chunks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {str(e)}")


@app.get("/search-jobs")
async def search_jobs(title: str, location: str = "", results: int = 10):
    """Searches for real, live job postings via our MCP job-search server,
    and logs the search to history via the ATS tracker MCP server."""
    try:
        async with stdio_client(JOB_SEARCH_SERVER_PARAMS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "search_jobs",
                    arguments={"title": title, "location": location, "results": results},
                )
                jobs = []
                for block in result.content:
                    if not block.text or not block.text.strip():
                        continue
                    try:
                        jobs.append(json.loads(block.text))
                    except json.JSONDecodeError:
                        continue

        search_id = None
        async with ats_stdio_client(ATS_SERVER_PARAMS) as (read2, write2):
            async with ATSClientSession(read2, write2) as session2:
                await session2.initialize()
                log_result = await session2.call_tool(
                    "log_search",
                    arguments={"search_title": title, "search_location": location, "results_count": len(jobs)},
                )
                search_id = json.loads(log_result.content[0].text)["id"]

        return {"status": "success", "count": len(jobs), "jobs": jobs, "search_id": search_id}
    except Exception as e:
        print("=== FULL TRACEBACK ===")
        traceback.print_exc()
        print("=======================")
        raise HTTPException(status_code=500, detail=f"Job search failed: {str(e)}")


class JobViewRequest(BaseModel):
    search_id: int
    job_id: str
    job_title: str
    company: str


@app.post("/log-job-view")
async def log_job_view(request: JobViewRequest):
    """Records that a specific job was opened/analyzed from a specific search."""
    try:
        async with ats_stdio_client(ATS_SERVER_PARAMS) as (read, write):
            async with ATSClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool("log_job_view", arguments=request.model_dump())
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log job view: {str(e)}")


class AnalyzeRequest(BaseModel):
    job_description: str


@app.post("/analyze")
async def analyze_job(request: AnalyzeRequest):
    """Runs the full tailoring pipeline against a specific job description."""
    try:
        extracted = await extract_job_requirements_async(request.job_description)

        if not extracted.requirements:
            raise HTTPException(status_code=400, detail="Could not extract any requirements from this job description")

        initial_state = {
            "job_requirements": extracted.requirements,
            "gap_report": None,
            "rewritten_bullets": [],
            "flagged_for_review": [],
        }
        final_state = tailoring_app.invoke(initial_state)

        return {
            "status": "success",
            "extracted_requirements": extracted.requirements,
            "min_years_experience": extracted.min_years_experience,
            "matched_skills": final_state["gap_report"].matched_skills,
            "missing_skills": final_state["gap_report"].missing_skills,
            "safe_rewrites": final_state["rewritten_bullets"],
            "flagged_for_review": [
                {
                    "chunk_id": item["chunk_id"],
                    "requirement": item["requirement"],
                    "original": item["original"],
                    "rewritten": item["rewritten"],
                    "reason": item["validation"]["fact_check"].get("unsupported_claims", []),
                }
                for item in final_state["flagged_for_review"]
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


class ApplyRequest(BaseModel):
    job_id: str
    job_title: str
    company: str
    safe_rewrites: List[dict] = []


@app.post("/apply-job")
async def apply_job(request: ApplyRequest):
    """Logs an application, including a summary of any resume rewrites
    that were applied before applying."""
    try:
        if request.safe_rewrites:
            summary = "; ".join([f"{r.get('requirement', 'unknown')}: rewritten" for r in request.safe_rewrites])
        else:
            summary = "No rewrites applied - resume used as-is"

        async with ats_stdio_client(ATS_SERVER_PARAMS) as (read, write):
            async with ATSClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "log_application",
                    arguments={
                        "job_id": request.job_id,
                        "job_title": request.job_title,
                        "company": request.company,
                        "tailored_resume_summary": summary,
                    },
                )
        return {"status": "success", "application": json.loads(result.content[0].text)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log application: {str(e)}")


@app.get("/rankings")
async def get_rankings(
    preferred_locations: str = "Pune,Nashik,Mumbai,Bangalore,Hyderabad,Remote",
    top_n: int = 12,
):
    """Runs the full two-stage ranking pipeline (Phase 7) against the
    historically-ingested job batch."""
    try:
        locations = [loc.strip() for loc in preferred_locations.split(",")]
        ranked = await rank_all_jobs_async(
            preferred_locations=locations, top_n_prefilter=top_n, max_concurrent=3,
        )
        return {"status": "success", "count": len(ranked), "rankings": [job.model_dump() for job in ranked]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ranking failed: {str(e)}")


class JobInput(BaseModel):
    job_id: str
    title: str
    company: str
    location: str
    description: str
    url: str


class RankJobsRequest(BaseModel):
    jobs: List[JobInput]
    preferred_locations: List[str] = ["Pune", "Nashik", "Mumbai", "Bangalore", "Hyderabad", "Remote"]


@app.post("/rank-searched-jobs")
async def rank_searched_jobs(request: RankJobsRequest):
    """Ranks the specific jobs passed in (e.g. from a live search), instead
    of the old frozen batch that /rankings uses."""
    try:
        jobs_dicts = [job.model_dump() for job in request.jobs]
        ranked = await rank_job_list_async(jobs_dicts, request.preferred_locations)
        return {"status": "success", "count": len(ranked), "rankings": [j.model_dump() for j in ranked]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ranking failed: {str(e)}")


@app.get("/history")
async def get_history():
    """Retrieves the full application history from the ATS tracker MCP server."""
    try:
        async with ats_stdio_client(ATS_SERVER_PARAMS) as (read, write):
            async with ATSClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_application_history", arguments={})
                history = [json.loads(block.text) for block in result.content]
        return {"status": "success", "count": len(history), "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")


@app.get("/search-history")
async def get_search_history():
    """Retrieves the full search history from the ATS tracker MCP server."""
    try:
        async with ats_stdio_client(ATS_SERVER_PARAMS) as (read, write):
            async with ATSClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_search_history", arguments={})
                history = [json.loads(block.text) for block in result.content]
        return {"status": "success", "count": len(history), "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch search history: {str(e)}")


@app.get("/search-history-detailed")
async def search_history_detailed():
    """Retrieves search history, with each search's viewed/analyzed jobs
    nested underneath it as a sub-section."""
    try:
        async with ats_stdio_client(ATS_SERVER_PARAMS) as (read, write):
            async with ATSClientSession(read, write) as session:
                await session.initialize()
                searches_result = await session.call_tool("get_search_history", arguments={})
                searches = [json.loads(block.text) for block in searches_result.content]

                for search in searches:
                    views_result = await session.call_tool(
                        "get_job_views_for_search", arguments={"search_id": search["id"]}
                    )
                    search["viewed_jobs"] = [json.loads(block.text) for block in views_result.content]

        return {"status": "success", "history": searches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch detailed search history: {str(e)}")