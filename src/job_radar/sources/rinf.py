import html
import re

from job_radar.client import HTTP


def fetch() -> list[dict]:
    """rinf.tech's own board, server-rendered HTML filtered to Timișoara. 10 jobs per page."""
    # ponytail: regex on the job-card markup; a redesign makes this return [] or raise, not mis-parse.
    jobs, page = {}, 1
    while True:
        text = HTTP.get("https://jobs.rinf.tech/", params={"city": "Timisoara", "page": page}).raise_for_status().text
        found = dict(re.findall(r'<a href="/(\d+)"><p[^>]*>([^<]+)</p></a>', text))
        # A page past the end repeats the last one, so stop when nothing is new.
        if not found.keys() - jobs.keys():
            return list(jobs.values())
        for id, title in found.items():
            jobs[id] = {"id": id, "title": html.unescape(title).strip(), "company": "rinf.tech",
                        "location": "Timisoara", "url": f"https://jobs.rinf.tech/{id}"}
        page += 1
