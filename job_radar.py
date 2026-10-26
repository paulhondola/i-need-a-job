"""Check employers' careers APIs for new Timișoara jobs and email the new ones."""
import argparse
import copy
import json
import os
import smtplib
import sys
import unicodedata
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path

import httpx


def matches_timisoara(location: str) -> bool:
    # NFKD splits both ș (comma) and ş (cedilla) into "s" + a combining mark.
    plain = "".join(c for c in unicodedata.normalize("NFKD", location) if not unicodedata.combining(c))
    plain = plain.casefold().strip()
    # ponytail: country-only "Romania" counts; these employers' Romanian office is in Timișoara
    return "timisoara" in plain or plain == "romania"


def update_state(state: dict, results: dict) -> tuple[dict, dict, list[str]]:
    """Diff fetch results against state. Returns (new_state, new_jobs_by_source, notes)."""
    state = copy.deepcopy(state)
    seen, broken = state["seen"], state["broken"]
    new_jobs, notes = {}, []
    for source, result in results.items():
        if isinstance(result, Exception):
            if source not in broken:
                broken.append(source)
                notes.append(f"{source} check broke: {result}")
            continue
        if source in broken:
            broken.remove(source)
            notes.append(f"{source} check recovered")
        jobs = {str(j["id"]): {**j, "id": str(j["id"])} for j in result}
        if source not in seen:
            seen[source] = sorted(jobs)
            continue
        fresh = [j for id, j in jobs.items() if id not in seen[source]]
        if fresh:
            new_jobs[source] = fresh
            seen[source] = sorted(set(seen[source]) | {j["id"] for j in fresh})
    state["broken"] = sorted(broken)
    return state, new_jobs, notes


def format_email(new_jobs: dict, notes: list[str]) -> tuple[str, str] | None:
    """Build (subject, body) grouped by company, or None when there is nothing to say."""
    if not new_jobs and not notes:
        return None
    by_company: dict[str, list[dict]] = {}
    for jobs in new_jobs.values():
        for j in jobs:
            by_company.setdefault(j["company"], []).append(j)
    companies = sorted(by_company)
    count = sum(len(v) for v in by_company.values())
    if count:
        subject = f"{count} new job{'s' if count != 1 else ''}: {', '.join(companies)}"
    else:
        subject = "job alert: " + "; ".join(notes)
    blocks = []
    for company in companies:
        lines = [company]
        for j in by_company[company]:
            lines += [f"- {j['title']} ({j['location']})", f"  {j['url']}"]
        blocks.append("\n".join(lines))
    if notes:
        blocks.append("\n".join(notes))
    return subject, "\n\n".join(blocks) + "\n"


def send_email(subject: str, body: str) -> None:
    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, user
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(user, os.environ["SMTP_PASS"])
        smtp.send_message(msg)


HTTP = httpx.Client(
    timeout=30,
    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"},
    follow_redirects=True,
)


def fetch_porsche() -> list[dict]:
    query = {
        "LanguageCode": "EN",
        "SearchParameters": {
            "FirstItem": 1,
            "CountItem": 500,
            "MatchedObjectDescriptor": ["ID", "PositionTitle", "PositionURI", "PositionLocation.CityName", "ParentOrganizationName"],
        },
        # 176 = Romania, 311 = Timișoara, channel 12 = public board (from jobs.porsche.com search URL)
        "SearchCriteria": [
            {"CriterionName": "PositionLocation.Country", "CriterionValue": ["176"]},
            {"CriterionName": "PositionLocation.City", "CriterionValue": ["311"]},
            {"CriterionName": "PublicationChannel.Code", "CriterionValue": ["12"]},
        ],
    }
    data = HTTP.get("https://porsche-beesite-production-gjb.app.beesite.de/search/", params={"data": json.dumps(query)}).raise_for_status().json()
    return [
        {
            "id": str(d["ID"]),
            "title": d["PositionTitle"],
            "company": d["ParentOrganizationName"],
            "location": d["PositionLocation"][0]["CityName"],
            "url": d["PositionURI"],
        }
        for d in (item["MatchedObjectDescriptor"] for item in data["SearchResult"]["SearchResultItems"])
    ]


def fetch_opswat() -> list[dict]:
    data = HTTP.get("https://boards-api.greenhouse.io/v1/boards/opswat/jobs").raise_for_status().json()
    return [
        {"id": str(j["id"]), "title": j["title"], "company": "OPSWAT", "location": j["location"]["name"], "url": j["absolute_url"]}
        for j in data["jobs"]
        if any(matches_timisoara(part) for part in j["location"]["name"].split(";"))
    ]


def fetch_nokia() -> list[dict]:
    url = "https://fa-evmr-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    jobs, offset = [], 0
    while True:
        params = {
            "onlyData": "true",
            "expand": "requisitionList.secondaryLocations",
            "finder": f"findReqs;siteNumber=CX_1,limit=200,offset={offset},sortBy=POSTING_DATES_DESC",
        }
        page = HTTP.get(url, params=params).raise_for_status().json()["items"][0]
        rows = page["requisitionList"]
        for r in rows:
            locations = [r["PrimaryLocation"]] + [s["Name"] for s in r.get("secondaryLocations", [])]
            if any(matches_timisoara(loc) for loc in locations):
                jobs.append({
                    "id": str(r["Id"]),
                    "title": r["Title"],
                    "company": "Nokia",
                    "location": "; ".join(locations),
                    "url": f"https://jobs.nokia.com/en/sites/CX_1/job/{r['Id']}",
                })
        offset += len(rows)
        if not rows or offset >= page["TotalJobsCount"]:
            return jobs


FETCHERS: dict[str, Callable[[], list[dict]]] = {
    "Porsche": fetch_porsche,
    "OPSWAT": fetch_opswat,
    "Nokia": fetch_nokia,
}


def run(fetchers: dict, state_path: Path, send: Callable[[str, str], None], save: bool = True) -> int:
    state = json.loads(state_path.read_text()) if state_path.exists() else {"seen": {}, "broken": []}
    results = {}
    for source, fetch in fetchers.items():
        try:
            results[source] = fetch()
        except Exception as e:  # one broken site must not stop the others
            print(f"{source}: {e!r}", file=sys.stderr)
            results[source] = e
    state, new_jobs, notes = update_state(state, results)
    for source, result in results.items():
        if not isinstance(result, Exception):
            print(f"{source}: {len(result)} jobs, {len(new_jobs.get(source, []))} new")
    email = format_email(new_jobs, notes)
    if email:
        try:
            send(*email)
        except Exception as e:
            print(f"sending email failed, state not saved: {e!r}", file=sys.stderr)
            return 1
    if save:
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the email instead of sending; don't save state")
    args = parser.parse_args()
    send = (lambda subject, body: print(f"Subject: {subject}\n\n{body}")) if args.dry_run else send_email
    return run(FETCHERS, Path(__file__).with_name("seen.json"), send, save=not args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
