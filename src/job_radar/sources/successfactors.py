import re
import xml.etree.ElementTree as ET

from job_radar.client import HTTP
from job_radar.state import matches_timisoara


def fetch(host: str, company: str) -> list[dict]:
    """SAP SuccessFactors career sites (e.g. careers.te.com). Titles look like "Process Engineer (TIMISOARA, TM, RO, 307160)"."""
    # Keyword search, then filter on the title's location. The feed returns 20 items unless "rows" is raised.
    feed = HTTP.get(f"https://{host}/services/rss/job/", params={"locale": "en_US", "keywords": "Timisoara", "rows": 500}).raise_for_status().text
    # The zero-results feed is a placeholder item, sometimes with a raw "&" (Huf) that breaks the XML parse.
    if "<title>No jobs currently available" in feed:
        return []
    jobs = []
    for item in ET.fromstring(feed).iter("item"):
        title, link = item.findtext("title").strip(), item.findtext("link").strip()
        m = re.match(r"(.*)\((.*)\)\s*$", title)
        name, location = (m.group(1).strip(), m.group(2)) if m else (title, "")
        if any(matches_timisoara(part) for part in location.split(",")):
            jobs.append({
                "id": re.search(r"/(\d+)/", link).group(1),
                "title": name,
                "company": company,
                "location": location,
                "url": link.split("?")[0],
            })
    return jobs
