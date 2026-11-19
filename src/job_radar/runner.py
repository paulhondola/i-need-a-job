import argparse
import sys
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

import job_radar
from job_radar.cities import DEFAULT_CITY_FILTER, CityFilter, parse_city_filter
from job_radar.filter import filter_jobs
from job_radar.mailer import format_email, send_email
from job_radar.sources import FETCHERS, Fetcher
from job_radar.state import collect_results


def run(
    fetchers: Mapping[str, Fetcher],
    send: Callable[[str, str], None],
    city_filter: CityFilter = DEFAULT_CITY_FILTER,
) -> int:
    print(f"cities: {city_filter.label}")
    results: dict[str, list[dict] | Exception] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            source: pool.submit(fetch, city_filter=city_filter)
            for source, fetch in fetchers.items()
        }
        for source, future in futures.items():
            try:
                results[source] = future.result()
            except Exception as e:  # noqa: BLE001 — one broken site must not stop the others
                print(f"{source}: {e!r}", file=sys.stderr)
                results[source] = e
    jobs, notes = collect_results(results)
    tiered_jobs, filter_notes = filter_jobs(jobs)
    notes.extend(filter_notes)
    email = format_email(tiered_jobs, notes, city_label=city_filter.label)
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
    parser.add_argument(
        "--city",
        action="append",
        metavar="CITY",
        help="Romanian city or comma-separated list (e.g. timisoara,cluj or all; default: Timișoara)",
    )
    args = parser.parse_args()
    try:
        city_filter = parse_city_filter(args.city)
    except ValueError as e:
        parser.error(str(e))
    send = (
        (lambda subject, body: print(f"Subject: {subject}\n\n{body}"))
        if args.dry_run
        else send_email
    )
    return run(FETCHERS, send, city_filter=city_filter)
