from job_radar.cities import DEFAULT_CITY_FILTER, CityFilter
from job_radar.client import HTTP


def fetch(
    slug: str,
    company: str,
    api_host: str = "api.lever.co",
    city_filter: CityFilter = DEFAULT_CITY_FILTER,
) -> list[dict]:
    """Lever postings API. EU-hosted boards (jobs.eu.lever.co) use api_host="api.eu.lever.co"."""
    postings = (
        HTTP.get(f"https://{api_host}/v0/postings/{slug}", params={"mode": "json"})
        .raise_for_status()
        .json()
    )
    jobs = []
    for p in postings:
        locations = p["categories"].get("allLocations") or [
            p["categories"].get("location") or ""
        ]
        if any(city_filter.matches(loc) for loc in locations):
            jobs.append(
                {
                    "id": p["id"],
                    "title": p["text"],
                    "company": company,
                    "location": "; ".join(locations),
                    "url": p["hostedUrl"],
                }
            )
    return jobs
