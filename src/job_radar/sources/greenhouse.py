from job_radar.client import HTTP
from job_radar.state import matches_timisoara


def fetch(board: str, company: str) -> list[dict]:
    data = (
        HTTP.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
        .raise_for_status()
        .json()
    )
    jobs = []
    for j in data["jobs"]:
        loc = (j.get("location") or {}).get("name") or ""
        if any(matches_timisoara(part) for part in loc.split(";")):
            jobs.append(
                {
                    "id": str(j["id"]),
                    "title": j["title"],
                    "company": company,
                    "location": loc,
                    "url": j["absolute_url"],
                }
            )
    return jobs
