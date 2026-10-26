from job_radar.client import HTTP
from job_radar.state import matches_timisoara


def fetch(api_host: str, site: str, job_url_prefix: str, company: str) -> list[dict]:
    """Oracle Recruiting Cloud. api_host is the *.oraclecloud.com host the careers site redirects to."""
    url = f"https://{api_host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    jobs, offset = [], 0
    while True:
        params = {
            "onlyData": "true",
            "expand": "requisitionList.secondaryLocations",
            "finder": f"findReqs;siteNumber={site},limit=200,offset={offset},sortBy=POSTING_DATES_DESC",
        }
        page = HTTP.get(url, params=params).raise_for_status().json()["items"][0]
        rows = page["requisitionList"]
        for r in rows:
            locations = [r["PrimaryLocation"]] + [s["Name"] for s in r.get("secondaryLocations", [])]
            if any(matches_timisoara(loc) for loc in locations):
                jobs.append({
                    "id": str(r["Id"]),
                    "title": r["Title"],
                    "company": company,
                    "location": "; ".join(locations),
                    "url": f"{job_url_prefix}{r['Id']}",
                })
        offset += len(rows)
        if not rows or offset >= page["TotalJobsCount"]:
            return jobs
