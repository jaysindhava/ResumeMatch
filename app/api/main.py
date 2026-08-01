import sys
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json

from pydantic import BaseModel
from app.agents.ranking import extract_job_requirements_async
from app.agents.tailoring_graph import tailoring_app

from app.agents.ranking import rank_all_jobs_async

from mcp import ClientSession as ATSClientSession, StdioServerParameters as ATSServerParameters
from mcp.client.stdio import stdio_client as ats_stdio_client

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI, UploadFile, File, HTTPException
import shutil

from app.parsers.resume_parser import (
    extract_raw_text,
    split_into_sections,
    chunk_bullets,
    chunk_skills,
    chunk_education,
    chunk_certifications,
)
from app.vectorstore.setup import get_resume_collection, embed_and_store

app = FastAPI(title="ResumeMatch API")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "data/resumes"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def health_check():
    """Simple health check - confirms the server is running."""
    return {"status": "ok", "message": "ResumeMatch API is running"}


@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """
    Accepts a PDF resume upload, saves it, and runs it through the full
    Phase 1-2 pipeline: parse -> chunk -> embed -> store in Chroma.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    save_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        text = extract_raw_text(save_path)
        sections = split_into_sections(text)

        all_chunks = []
        all_chunks += chunk_bullets(sections.get("professional_experience", ""), "professional_experience")
        all_chunks += chunk_bullets(sections.get("projects", ""), "projects")
        all_chunks += chunk_skills(sections.get("skills", ""))
        all_chunks += chunk_education(sections.get("education", ""))
        all_chunks += chunk_certifications(sections.get("certifications", ""))

        collection = get_resume_collection()
        embed_and_store(all_chunks, collection)

        return {
            "status": "success",
            "filename": file.filename,
            "chunks_created": len(all_chunks),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {str(e)}")


import traceback

@app.get("/search-jobs")
async def search_jobs(title: str, location: str = "", results: int = 10):
    """
    Searches for real, live job postings via our MCP job-search server,
    and logs the search to history via the ATS tracker MCP server.
    """
    try:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["app/mcp_servers/job_search_server.py"],
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "search_jobs",
                    arguments={"title": title, "location": location, "results": results},
                )
                jobs = []
                for block in result.content:
                    if not block.text or not block.text.strip():
                        continue  # skip empty content blocks instead of crashing
                    try:
                        jobs.append(json.loads(block.text))
                    except json.JSONDecodeError:
                        continue  # skip any block that isn't valid JSON, rather than failing the whole request

        ats_params = ATSServerParameters(command=sys.executable, args=["app/mcp_servers/ats_tracker_server.py"])
        async with ats_stdio_client(ats_params) as (read2, write2):
            async with ATSClientSession(read2, write2) as session2:
                await session2.initialize()
                await session2.call_tool(
                    "log_search",
                    arguments={"search_title": title, "search_location": location, "results_count": len(jobs)},
                )

        return {"status": "success", "count": len(jobs), "jobs": jobs}
    except Exception as e:
        print("=== FULL TRACEBACK ===")
        traceback.print_exc()
        print("=======================")
        raise HTTPException(status_code=500, detail=f"Job search failed: {str(e)}")



class AnalyzeRequest(BaseModel):
    job_description: str


@app.post("/analyze")
async def analyze_job(request: AnalyzeRequest):
    """
    Runs the full tailoring pipeline against a specific job description:
    extracts requirements, runs isolated gap analysis, attempts safe
    rewrites, and returns matched/missing skills plus any safe rewrites
    or flagged-for-review items.
    """
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

    


@app.get("/rankings")
async def get_rankings(
    preferred_locations: str = "Pune,Nashik,Mumbai,Bangalore,Hyderabad,Remote",
    top_n: int = 12,
):
    """
    Runs the full two-stage ranking pipeline (Phase 7): cheap embedding
    pre-filter across all ingested jobs, followed by deep LLM-based scoring
    on the top candidates only.
    """
    try:
        locations = [loc.strip() for loc in preferred_locations.split(",")]
        ranked = await rank_all_jobs_async(
            preferred_locations=locations,
            top_n_prefilter=top_n,
            max_concurrent=3,
        )

        return {
            "status": "success",
            "count": len(ranked),
            "rankings": [job.model_dump() for job in ranked],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ranking failed: {str(e)}")

    

@app.get("/history")
async def get_history():
    """
    Retrieves the full application history from the ATS tracker MCP server
    (Phase 8) - this is the project's persistent memory layer.
    """
    try:
        server_params = ATSServerParameters(
            command=sys.executable,
            args=["app/mcp_servers/ats_tracker_server.py"],
        )

        async with ats_stdio_client(server_params) as (read, write):
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
        server_params = ATSServerParameters(command=sys.executable, args=["app/mcp_servers/ats_tracker_server.py"])
        async with ats_stdio_client(server_params) as (read, write):
            async with ATSClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_search_history", arguments={})
                history = [json.loads(block.text) for block in result.content]

        return {"status": "success", "count": len(history), "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch search history: {str(e)}")