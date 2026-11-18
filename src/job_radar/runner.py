import argparse
import sys
from collections.abc import Callable

import job_radar
from job_radar.mailer import format_email, send_email
from job_radar.sources import FETCHERS
from job_radar.state import collect_results


def run(fetchers: dict, send: Callable[[str, str], None]) -> int:
    results = {}
    for source, fetch in fetchers.items():
        try:
            results[source] = fetch()
        except Exception as e:  # one broken site must not stop the others
            print(f"{source}: {e!r}", file=sys.stderr)
            results[source] = e
    jobs, notes = collect_results(results)
    for source, result in results.items():
        if not isinstance(result, Exception):
            print(f"{source}: {len(jobs.get(source, []))} jobs")
    email = format_email(jobs, notes)
    if email:
        try:
            send(*email)
        except Exception as e:
            print(f"sending email failed: {e!r}", file=sys.stderr)
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="job_radar", description=job_radar.__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the email instead of sending")
    args = parser.parse_args()
    send = (lambda subject, body: print(f"Subject: {subject}\n\n{body}")) if args.dry_run else send_email
    return run(FETCHERS, send)

