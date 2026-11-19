from job_radar.cities import DEFAULT_CITY_FILTER, CityFilter
from job_radar.client import HTTP


def fetch(city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]:
    """Deutsche Telekom's careers.telekom.com search API (Eightfold behind a proxy). 20 jobs per page."""
    jobs, page = [], 1
    while True:
        data = (
            HTTP.post(
                "https://careers.telekom.com/api/jobs-proxy/search",
                params={"location": "Romania", "page": page},
                json={"user_query": "", "locale": "en"},
            )
            .raise_for_status()
            .json()
        )
        for p in data["data"]:
            city = p.get("city") or ""
            if city_filter.is_all or city_filter.matches(city):
                jobs.append(
                    {
                        "id": p["requisition_id"],
                        "title": p["title"],
                        "company": "Deutsche Telekom",
                        "location": city,
                        "url": f"https://careers.telekom.com/en/jobs/{p['requisition_id']}",
                    }
                )
        if not data["data"] or page >= data["pagination_info"]["number_of_pages"]:
            return jobs
        page += 1
