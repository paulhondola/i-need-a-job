from job_radar.cities import DEFAULT_CITY_FILTER, CityFilter
from job_radar.client import HTTP


def fetch(
    board: str, company: str, city_filter: CityFilter = DEFAULT_CITY_FILTER
) -> list[dict]:
    data = (
        HTTP.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
        .raise_for_status()
        .json()
    )
    jobs = []
    for j in data["jobs"]:
        loc = (j.get("location") or {}).get("name") or ""
        if any(city_filter.matches(part) for part in loc.split(";")):
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
