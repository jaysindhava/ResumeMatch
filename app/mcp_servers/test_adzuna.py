import os
import requests
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")


def search_jobs_raw(title: str, location: str = "", results: int = 5, country: str = "in"):
    """Direct call to the Adzuna API, no MCP wrapper yet - just proving it works."""
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "results_per_page": results,
        "what": title,
        "where": location,
        "content-type": "application/json",
    }

    response = requests.get(url, params=params)
    response.raise_for_status()  # raises an error immediately if the call failed
    return response.json()


if __name__ == "__main__":
    print("Testing Adzuna API...")
    data = search_jobs_raw(title="python developer", location="Pune")

    print(f"\nTotal jobs found (matching count): {data.get('count')}")
    print(f"Results returned: {len(data.get('results', []))}\n")

    for job in data.get("results", []):
        print(f"Title: {job.get('title')}")
        print(f"Company: {job.get('company', {}).get('display_name')}")
        print(f"Location: {job.get('location', {}).get('display_name')}")
        print(f"URL: {job.get('redirect_url')}")
        print(f"Description snippet: {job.get('description', '')[:150]}...")
        print("-" * 60)