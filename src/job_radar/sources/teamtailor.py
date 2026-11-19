import xml.etree.ElementTree as ET

from job_radar.cities import DEFAULT_CITY_FILTER, CityFilter
from job_radar.client import HTTP

TT = "{https://teamtailor.com/locations}"


def fetch(
    slug: str, company: str, city_filter: CityFilter = DEFAULT_CITY_FILTER
) -> list[dict]:
    feed = HTTP.get(f"https://{slug}.teamtailor.com/jobs.rss").raise_for_status().text
    jobs = []
    for item in ET.fromstring(feed).iter("item"):
        cities = [c.text or "" for c in item.iter(f"{TT}city")]
        if any(city_filter.matches(c) for c in cities):
            link = item.findtext("link", "")
            jobs.append(
                {
                    "id": link.rsplit("/", 1)[-1].split("-", 1)[0],
                    "title": item.findtext("title", ""),
                    "company": company,
                    "location": "; ".join(cities),
                    "url": link,
                }
            )
    return jobs
