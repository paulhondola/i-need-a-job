"""Check employers' careers APIs for new Timișoara jobs and email the new ones."""
import copy
import os
import smtplib
import unicodedata
from email.message import EmailMessage


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
