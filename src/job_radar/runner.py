import argparse
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

import job_radar
from job_radar.filter import filter_jobs
from job_radar.mailer import format_email, send_email
from job_radar.sources import FETCHERS
from job_radar.state import collect_results


def run(fetchers: dict, send: Callable[[str, str], None]) -> int:
    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {source: pool.submit(fetch) for source, fetch in fetchers.items()}
        for source, future in futures.items():
            try:
                results[source] = future.result()
            except Exception as e:  # noqa: BLE001 — one broken site must not stop the others
                print(f"{source}: {e!r}", file=sys.stderr)
                results[source] = e
    jobs, notes = collect_results(results)
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
