import html
import re

from job_radar.cities import DEFAULT_CITY_FILTER, CityFilter
from job_radar.client import HTTP

_JOB_CARD_RE = re.compile(r'<a href="/(\d+)"><p[^>]*>([^<]+)</p></a>')
_CITY_CHECKBOX_RE = re.compile(r'name="city-[^"]*"[^>]*>\s*<span[^>]*>([^<]+)<span')


def _paginate(params: dict[str, str]) -> dict[str, str]:
    found_all: dict[str, str] = {}
    page = 1
    while True:
        text = (
            HTTP.get("https://jobs.rinf.tech/", params={**params, "page": page})
            .raise_for_status()
            .text
        )
        found = dict(_JOB_CARD_RE.findall(text))
        # A page past the end repeats the last one, so stop when nothing is new.
        if not found.keys() - found_all.keys():
            return found_all
        found_all.update(found)
        page += 1


def fetch(city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]:
    """rinf.tech's own board, server-rendered HTML. 10 jobs per page."""
    # ponytail: regex on the job-card markup; a redesign makes this raise or return [], not mis-parse.
    if city_filter.is_all:
        found = _paginate({"country": "Romania"})
        return [
            {
                "id": job_id,
                "title": html.unescape(title).strip(),
                "company": "rinf.tech",
                "location": "Romania",
                "url": f"https://jobs.rinf.tech/{job_id}",
            }
            for job_id, title in found.items()
        ]

    landing = HTTP.get("https://jobs.rinf.tech/").raise_for_status().text
    available_cities = [
        html.unescape(c).strip() for c in _CITY_CHECKBOX_RE.findall(landing)
    ]
    if not available_cities:
        raise ValueError("no city filters found on rinf.tech")

    matched_cities = [c for c in available_cities if city_filter.matches(c)]
    jobs: dict[str, dict] = {}
    job_cities: dict[str, list[str]] = {}
    for city_name in matched_cities:
        for job_id, title in _paginate({"city": city_name}).items():
            if job_id not in jobs:
                job_cities[job_id] = [city_name]
                jobs[job_id] = {
                    "id": job_id,
                    "title": html.unescape(title).strip(),
                    "company": "rinf.tech",
                    "location": city_name,
                    "url": f"https://jobs.rinf.tech/{job_id}",
                }
            elif city_name not in job_cities[job_id]:
                job_cities[job_id].append(city_name)
                jobs[job_id]["location"] = "; ".join(job_cities[job_id])
    return list(jobs.values())
