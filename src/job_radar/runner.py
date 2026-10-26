import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

import job_radar
from job_radar.mailer import format_email, send_email
from job_radar.sources import FETCHERS
from job_radar.state import update_state


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
    parser = argparse.ArgumentParser(prog="job_radar", description=job_radar.__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the email instead of sending; don't save state")
    parser.add_argument("--state", type=Path, default=Path("seen.json"), help="state file (default: ./seen.json)")
    args = parser.parse_args()
    send = (lambda subject, body: print(f"Subject: {subject}\n\n{body}")) if args.dry_run else send_email
    return run(FETCHERS, args.state, send, save=not args.dry_run)
