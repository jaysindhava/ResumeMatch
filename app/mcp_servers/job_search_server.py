import os
import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

APP_ID = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")

# Create the MCP server instance
mcp = FastMCP("job-search-mcp")


@mcp.tool()
def search_jobs(title: str, location: str = "", results: int = 10, country: str = "in") -> list[dict]:
    """
    Search for real, current job postings using the Adzuna API.

    Args:
        title: Job title or keywords to search for (e.g. "python developer")
        location: City or region to search in (e.g. "Pune"). Leave empty for nationwide.
        results: Number of results to return (default 10, max ~50)
        country: Two-letter country code (default "in" for India)

    Returns:
        A list of job postings, each with title, company, location, url, and description.
    """
    app_id = os.getenv("ADZUNA_APP_ID") or APP_ID
    app_key = os.getenv("ADZUNA_APP_KEY") or APP_KEY

    if not app_id or not app_key:
        raise ValueError(f"Adzuna API credentials missing: app_id={bool(app_id)}, app_key={bool(app_key)}")

    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": results,
        "what": title,
        "where": location,
        "content-type": "application/json",
    }

    response = requests.get(url, params=params)
    print(f"DEBUG: Adzuna response status={response.status_code}, body={response.text[:300]}")
    response.raise_for_status()
    data = response.json()

    jobs = []
    for job in data.get("results", []):
        jobs.append({
            "job_id": str(job.get("id")),
            "title": job.get("title"),
            "company": job.get("company", {}).get("display_name"),
            "location": job.get("location", {}).get("display_name"),
            "description": job.get("description"),
            "url": job.get("redirect_url"),
            "posted_date": job.get("created"),
        })

    return jobs


if __name__ == "__main__":
    # Run the MCP server (stdio transport - simplest for local testing)
    mcp.run(transport="stdio")