from job_radar.client import HTTP
from job_radar.state import matches_timisoara


def fetch(board: str, company: str) -> list[dict]:
    data = HTTP.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs").raise_for_status().json()
    return [
        {"id": str(j["id"]), "title": j["title"], "company": company, "location": j["location"]["name"], "url": j["absolute_url"]}
        for j in data["jobs"]
        if any(matches_timisoara(part) for part in j["location"]["name"].split(";"))
    ]
