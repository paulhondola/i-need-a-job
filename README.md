# i-need-a-job

Checks employers' careers APIs every 3 hours for Timișoara roles and emails the new ones (GitHub Actions, `.github/workflows/check.yml`).

- Run tests: `uv run pytest`
- Try it locally without sending or saving: `uv run python -m job_radar --dry-run`
- Secrets: `SMTP_USER` (your Gmail address) and `SMTP_PASS` (a Gmail App Password).

## Layout

- `src/job_radar/sources/__init__.py`: the company list, one line per company.
- `src/job_radar/sources/<system>.py`: one fetcher per hiring system (Greenhouse, Workday, Oracle) or custom site (BeeSite for Porsche). Each returns `{id, title, company, location, url}` dicts.
- `src/job_radar/state.py`: Timișoara matching and the "what's new" diff. `mailer.py`: the email. `runner.py`: one run.

## Changing companies

- Company on a known system: add one line to `FETCHERS`. Its first run is silent.
- New system: add `sources/<system>.py` with a `fetch(...)` and register the company.
- Changed a company's filter? Delete its key from `seen.json` in the same commit so it re-seeds silently.
- A company that starts failing gets one "check broke" email and one "recovered" email; it's listed under `broken` in `seen.json` meanwhile.
- Pending: Haufe (its job board's search API rejects requests right now).
