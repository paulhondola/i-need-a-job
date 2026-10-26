from job_radar.client import HTTP
from job_radar.state import matches_timisoara


def fetch() -> list[dict]:
    """Deutsche Telekom's careers.telekom.com search API (Eightfold behind a proxy). 20 jobs per page."""
    jobs, page = [], 1
    while True:
        data = HTTP.post(
            "https://careers.telekom.com/api/jobs-proxy/search",
            params={"location": "Timișoara", "page": page},  # its location filter wants the diacritic spelling
            json={"user_query": "", "locale": "en"},
        ).raise_for_status().json()
        for p in data["data"]:
            if any(matches_timisoara(c) for c in p["city"].split(",")):
                jobs.append({
                    "id": p["requisition_id"],
                    "title": p["title"],
                    "company": "Deutsche Telekom",
                    "location": p["city"],
                    "url": f"https://careers.telekom.com/en/jobs/{p['requisition_id']}",
                })
        if page >= data["pagination_info"]["number_of_pages"]:
            return jobs
        page += 1
