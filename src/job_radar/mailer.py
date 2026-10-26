import os
import smtplib
from email.message import EmailMessage


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
    # Email headers can't contain newlines; httpx error messages do.
    return " ".join(subject.split()), "\n\n".join(blocks) + "\n"


def send_email(subject: str, body: str) -> None:
    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, user
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(user, os.environ["SMTP_PASS"])
        smtp.send_message(msg)
