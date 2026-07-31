import sys
import os
import asyncio

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json

from app.parsers.job_parser import chunk_job_description
from app.vectorstore.setup import get_job_collection, embed_and_store


async def fetch_jobs_via_mcp(title: str, location: str, results: int = 10) -> list[dict]:
    """Connect to our job_search_server MCP server and call search_jobs."""
    server_params = StdioServerParameters(
        command="python",
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
            for content_block in result.content:
                jobs.append(json.loads(content_block.text))
            return jobs


async def main():
    # A handful of search queries to build up a varied test set of postings.
    # Feel free to adjust these to match roles you're actually targeting.
    search_queries = [
        ("python developer", "Pune"),
        ("machine learning engineer", "Pune"),
        ("backend developer", "Pune"),
        ("full stack developer", "Pune"),
    ]

    all_jobs = {}  # keyed by job_id to automatically de-duplicate

    for title, location in search_queries:
        print(f"Fetching jobs for: '{title}' in {location}...")
        jobs = await fetch_jobs_via_mcp(title, location, results=8)
        for job in jobs:
            all_jobs[job["job_id"]] = job

    print(f"\nTotal unique jobs collected: {len(all_jobs)}")

    all_chunks = []
    for job in all_jobs.values():
        chunks = chunk_job_description(
            text=job["description"],
            job_id=job["job_id"],
            title=job["title"],
            company=job["company"],
            location=job["location"],
            url=job["url"],
        )
        all_chunks += chunks

    print(f"Total chunks created: {len(all_chunks)}")

    print("\nEmbedding and storing in Chroma...")
    collection = get_job_collection()
    embed_and_store(all_chunks, collection)
    print(f"✅ Stored {len(all_chunks)} chunks in the 'job_chunks' collection.")
    print(f"Collection now contains {collection.count()} total items.")


if __name__ == "__main__":
    asyncio.run(main())