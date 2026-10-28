from job_radar.client import HTTP
from job_radar.state import matches_timisoara


def fetch(slug: str, company: str) -> list[dict]:
    # The API's own city filter doesn't fold diacritics ("Timisoara" misses "Timișoara"), so filter by country only.
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    jobs, offset = [], 0
    while True:
        page = HTTP.get(url, params={"country": "ro", "limit": 100, "offset": offset}).raise_for_status().json()
        for p in page["content"]:
            # Remote roles count too: the query is already limited to Romania.
            if p["location"].get("remote") or matches_timisoara(p["location"].get("city") or ""):
                jobs.append({
                    "id": p["id"],
                    "title": p["name"],
                    "company": company,
                    "location": p["location"].get("fullLocation") or p["location"]["city"],
                    "url": f"https://jobs.smartrecruiters.com/{p['company']['identifier']}/{p['id']}",
                })
        offset += len(page["content"])
        if not page["content"] or offset >= page["totalFound"]:
            return jobs
