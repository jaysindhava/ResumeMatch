import sqlite3
import os
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# In production (ECS + EFS), set ATS_DB_PATH to point to the EFS mount.
# Defaults to a sibling file next to this script for local dev.
DB_PATH = os.getenv("ATS_DB_PATH", os.path.join(os.path.dirname(__file__), "ats.db"))

mcp = FastMCP("ats-tracker-mcp")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, job_title TEXT, company TEXT,
        tailored_resume_summary TEXT, status TEXT DEFAULT 'tailored', created_at TEXT, updated_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, search_title TEXT, search_location TEXT,
        results_count INTEGER, created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS job_views (
        id INTEGER PRIMARY KEY AUTOINCREMENT, search_id INTEGER, job_title TEXT, company TEXT,
        job_id TEXT, created_at TEXT,
        UNIQUE(search_id, job_id))""")
    conn.commit()
    conn.close()


init_db()  # runs once when the server starts


@mcp.tool()
def log_application(job_id: str, job_title: str, company: str, tailored_resume_summary: str) -> dict:
    """
    Log that a resume was tailored for a specific job. Creates a new
    application record with status 'tailored'.

    Args:
        job_id: The Adzuna job ID this tailoring was done for
        job_title: The job's title
        company: The hiring company
        tailored_resume_summary: A short summary of what was tailored (e.g. which bullets changed)

    Returns:
        The newly created application record, including its id and timestamps.
    """
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        """INSERT INTO applications (job_id, job_title, company, tailored_resume_summary, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'tailored', ?, ?)""",
        (job_id, job_title, company, tailored_resume_summary, now, now),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return {
        "id": new_id,
        "job_id": job_id,
        "job_title": job_title,
        "company": company,
        "status": "tailored",
        "created_at": now,
    }


@mcp.tool()
def get_application_history() -> list[dict]:
    """
    Retrieve all past application records, most recent first.

    Returns:
        A list of application records with id, job details, status, and timestamps.
    """
    conn = get_connection()
    rows = conn.execute("SELECT * FROM applications ORDER BY created_at DESC").fetchall()
    conn.close()

    return [dict(row) for row in rows]


@mcp.tool()
def update_status(application_id: int, new_status: str) -> dict:
    """
    Update the status of an application (e.g. 'applied', 'interview', 'rejected', 'offer').

    Args:
        application_id: The id of the application record to update
        new_status: The new status value

    Returns:
        The updated application record.
    """
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE applications SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, now, application_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (application_id,)).fetchone()
    conn.close()

    if row is None:
        return {"error": f"No application found with id {application_id}"}
    return dict(row)

@mcp.tool()
def log_search(search_title: str, search_location: str, results_count: int) -> dict:
    """
    Logs that a job search happened, for the user's search history.

    Args:
        search_title: The job title/keywords searched for
        search_location: The location searched in
        results_count: How many results were returned

    Returns:
        The newly created search history record.
    """
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        "INSERT INTO search_history (search_title, search_location, results_count, created_at) VALUES (?, ?, ?, ?)",
        (search_title, search_location, results_count, now),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return {"id": new_id, "search_title": search_title, "search_location": search_location, "results_count": results_count, "created_at": now}


@mcp.tool()
def get_search_history() -> list[dict]:
    """Retrieve all past searches, most recent first."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM search_history ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]

@mcp.tool()
def log_job_view(search_id: int, job_id: str, job_title: str, company: str) -> dict:
    """Records that a specific job was opened/analyzed from a specific search.
    Uses INSERT OR IGNORE with a UNIQUE(search_id, job_id) constraint so this
    is safe even under a race condition (e.g. React StrictMode firing the
    same effect twice almost simultaneously in development)."""
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO job_views (search_id, job_title, company, job_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (search_id, job_title, company, job_id, now),
    )
    conn.commit()
    conn.close()
    return {"search_id": search_id, "job_id": job_id, "job_title": job_title}

@mcp.tool()
def get_job_views_for_search(search_id: int) -> list[dict]:
    """Returns all jobs viewed/analyzed under a given search."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM job_views WHERE search_id = ?", (search_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    mcp.run(transport="stdio")