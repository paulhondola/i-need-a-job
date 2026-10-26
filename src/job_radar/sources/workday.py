from job_radar.client import HTTP
from job_radar.state import matches_timisoara


def fetch(host: str, tenant: str, site: str, company: str) -> list[dict]:
    """host e.g. "intel.wd1.myworkdayjobs.com", tenant "intel", site "External"."""
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    body = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
    facets = HTTP.post(url, json=body).raise_for_status().json()["facets"]
    # Raises KeyError/StopIteration if Workday changes the facet shape (better than silently returning []).
    group = next(f for f in facets if f["facetParameter"] == "locationMainGroup")
    locations = next(g for g in group["values"] if g["facetParameter"] == "locations")["values"]
    matched = [v for v in locations if matches_timisoara(v["descriptor"])]
    ids = [v["id"] for v in matched]
    if not ids:
        return []
    body["appliedFacets"] = {"locations": ids}
    jobs = []
    while True:
        page = HTTP.post(url, json=body).raise_for_status().json()
        for p in page["jobPostings"]:
            jobs.append({
                "id": p["externalPath"].rsplit("_", 1)[-1],
                "title": p["title"],
                "company": company,
                "location": p.get("locationsText") or "; ".join(v["descriptor"] for v in matched),
                "url": f"https://{host}/{site}{p['externalPath']}",
            })
        body["offset"] += 20
        if not page["jobPostings"] or body["offset"] >= page["total"]:
            return jobs
