import xml.etree.ElementTree as ET

from job_radar.client import HTTP
from job_radar.state import matches_timisoara


def fetch(slug: str, company: str, tld: str = "de", job_url: str = "") -> list[dict]:
    """job_url: link format with {id}; companies that hide Personio's hosted page link to their own site."""
    job_url = job_url or f"https://{slug}.jobs.personio.{tld}/job/{{id}}"
    root = ET.fromstring(HTTP.get(f"https://{slug}.jobs.personio.{tld}/xml").raise_for_status().text)
    jobs = []
    for p in root.iter("position"):
        offices = [p.findtext("office") or ""] + [o.text or "" for o in p.iterfind("additionalOffices/office")]
        if any(matches_timisoara(o) for o in offices):
            jobs.append({
                "id": p.findtext("id"),
                "title": p.findtext("name"),
                "company": company,
                "location": "; ".join(o for o in offices if o),
                "url": job_url.format(id=p.findtext("id")),
            })
    return jobs
