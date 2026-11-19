import html
import re
import xml.etree.ElementTree as ET

from job_radar.client import HTTP
from job_radar.state import matches_timisoara


def fetch(host: str, company: str) -> list[dict]:
    """SAP SuccessFactors career sites (e.g. careers.te.com). Titles look like "Process Engineer (TIMISOARA, TM, RO, 307160)"."""
    # Keyword search, then filter on the title's location. The feed returns 20 items unless "rows" is raised.
    feed = (
        HTTP.get(
            f"https://{host}/services/rss/job/",
            params={"locale": "en_US", "keywords": "Timisoara", "rows": 500},
        )
        .raise_for_status()
        .text
    )
    # SuccessFactors feeds can contain raw "&" in descriptions (e.g. Huf, EY) that break XML parsing.
    feed = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", feed)
    jobs = []
    for item in ET.fromstring(feed).iter("item"):
        title, link = (
            item.findtext("title", "").strip(),
            item.findtext("link", "").strip(),
        )
        m = re.match(r"(.*)\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$", title, re.DOTALL)
        name, location = (m.group(1).strip(), m.group(2)) if m else (title, "")
        if matches_timisoara(location):
            job_id = re.search(r"/(\d+)/", link)
            if job_id is None:
                raise ValueError(f"missing job id in {link!r}")
            jobs.append(
                {
                    "id": job_id.group(1),
                    "title": html.unescape(name),
                    "company": company,
                    "location": location,
                    "url": link.split("?")[0],
                }
            )
    return jobs
