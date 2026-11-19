import html
import re
import xml.etree.ElementTree as ET

from job_radar.cities import DEFAULT_CITY_FILTER, CityFilter
from job_radar.client import HTTP


def fetch(
    host: str, company: str, city_filter: CityFilter = DEFAULT_CITY_FILTER
) -> list[dict]:
    """SAP SuccessFactors career sites (e.g. careers.te.com). Titles look like "Process Engineer (TIMISOARA, TM, RO, 307160)"."""
    # Keyword search per term, then filter on the title's location. The feed returns 20 items unless "rows" is raised.
    jobs: dict[str, dict] = {}
    for kw in city_filter.search_terms():
        feed = (
            HTTP.get(
                f"https://{host}/services/rss/job/",
                params={"locale": "en_US", "keywords": kw, "rows": 500},
            )
            .raise_for_status()
            .text
        )
        # SuccessFactors feeds can contain raw "&" in descriptions (e.g. Huf, EY) that break XML parsing.
        feed = re.sub(
            r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", feed
        )
        for item in ET.fromstring(feed).iter("item"):
            title, link = (
                item.findtext("title", "").strip(),
                item.findtext("link", "").strip(),
            )
            m = re.match(r"(.*)\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$", title, re.DOTALL)
            name, location = (m.group(1).strip(), m.group(2)) if m else (title, "")
            if city_filter.matches(location):
                job_id_match = re.search(r"/(\d+)/", link)
                if job_id_match is None:
                    raise ValueError(f"missing job id in {link!r}")
                job_id = job_id_match.group(1)
                if job_id not in jobs:
                    jobs[job_id] = {
                        "id": job_id,
                        "title": html.unescape(name),
                        "company": company,
                        "location": location,
                        "url": link.split("?")[0],
                    }
    return list(jobs.values())
