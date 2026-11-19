import os
import smtplib
from email.message import EmailMessage


def _format_tier_block(header: str, jobs: list[dict]) -> str:
    """Render one tier header followed by company-grouped job entries."""
    by_company: dict[str, list[dict]] = {}
    for j in jobs:
        by_company.setdefault(j["company"], []).append(j)
    blocks = [header]
    for company in sorted(by_company):
        lines = [company]
        for j in by_company[company]:
            lines += [f"- {j['title']} ({j['location']})", f"  {j['url']}"]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def format_email(
    tiered_jobs: dict[str, list[dict]], notes: list[str]
) -> tuple[str, str] | None:
    """Build (subject, body) grouped by tier then company, or None when there is nothing to say."""
    best = tiered_jobs.get("best", [])
    other = tiered_jobs.get("other", [])
    if not best and not other and not notes:
        return None

    companies = sorted({j["company"] for j in (*best, *other)})
    if best and other:
        subject = f"{len(best)} best, {len(other)} other jobs: {', '.join(companies)}"
    elif best:
        subject = f"{len(best)} best job{'s' if len(best) != 1 else ''}: {', '.join(companies)}"
    elif other:
        subject = (
            f"{len(other)} job{'s' if len(other) != 1 else ''}: {', '.join(companies)}"
        )
    else:
        subject = "job alert: " + "; ".join(notes)

    blocks = []
    if best:
        blocks.append(_format_tier_block(f"=== BEST MATCHES ({len(best)}) ===", best))
    if other:
        blocks.append(
            _format_tier_block(f"=== OTHER TECH ROLES ({len(other)}) ===", other)
        )
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
