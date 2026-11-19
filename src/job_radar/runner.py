import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

import job_radar
from job_radar.filter import filter_jobs
from job_radar.mailer import format_email, send_email
from job_radar.sources import FETCHERS
from job_radar.state import collect_results

DEFAULT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_dotenv(path: Path = DEFAULT_ENV_PATH) -> None:
    """Populate os.environ from a .env file without overriding existing variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def run(fetchers: dict, send: Callable[[str, str], None]) -> int:
    results = {}
    for source, fetch in fetchers.items():
        try:
            results[source] = fetch()
        except Exception as e:  # noqa: BLE001 — one broken site must not stop the others
            print(f"{source}: {e!r}", file=sys.stderr)
            results[source] = e
    jobs, notes = collect_results(results)
    for source, result in results.items():
        if not isinstance(result, Exception):
            print(f"{source}: {len(jobs.get(source, []))} jobs")
    tiered_jobs, filter_notes = filter_jobs(jobs)
    notes.extend(filter_notes)
    email = format_email(tiered_jobs, notes)
    if email:
        try:
            send(*email)
        except Exception as e:  # noqa: BLE001
            print(f"sending email failed: {e!r}", file=sys.stderr)
            return 1
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="job_radar", description=job_radar.__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="print the email instead of sending"
    )
    args = parser.parse_args()
    send = (
        (lambda subject, body: print(f"Subject: {subject}\n\n{body}"))
        if args.dry_run
        else send_email
    )
    return run(FETCHERS, send)
