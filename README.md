# i-need-a-job

Checks employers' careers APIs every day for Timișoara roles and emails the current offers (GitHub Actions, `.github/workflows/check.yml`).

- Run tests: `uv run pytest`
- Try it locally without sending: `uv run python -m job_radar --dry-run`
- Secrets: `SMTP_USER` (your Gmail address) and `SMTP_PASS` (a Gmail App Password).

## Layout

- `src/job_radar/sources/__init__.py`: the company list, one line per company.
- `src/job_radar/sources/<system>.py`: one fetcher per hiring system (Greenhouse, Workday, Oracle, SuccessFactors, ...) or custom site (Porsche, Telekom, rinf.tech). Each returns `{id, title, company, location, url}` dicts.
- `src/job_radar/state.py`: Timișoara matching and result collection. `mailer.py`: the email. `runner.py`: one run.

## Changing companies

- Company on a known system: add one line to `FETCHERS`.
- New system: add `sources/<system>.py` with a `fetch(...)` and register the company.
- A company that fails during a run is noted at the bottom of that day's email (`<source> check broke: ...`).
- Pending: Haufe (its job board's search API rejects requests right now).
- Not tracked: Hella (its job list loads only through a session-token API; its site offers its own "Create an alert" emails), Cognizant, Infosys, SafeFleet (block scripted requests), Luxoft (no Timișoara roles listed).

