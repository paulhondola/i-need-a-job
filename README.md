# i-need-a-job

Checks employers' careers APIs every day for Timișoara roles and emails the current offers (GitHub Actions, `.github/workflows/check.yml`).

- Run tests: `uv run pytest`
- Try it locally without sending: `uv run python -m job_radar --dry-run`
- Secrets: `SMTP_USER` (your Gmail address), `SMTP_PASS` (a Gmail App Password), and `LLM_API_KEY` (for LLM preference tiering; falls back to regex-only filtering with an error note if missing). Optional provider overrides: `LLM_BASE_URL`, `LLM_MODEL`. For local runs, put them in `.env` (gitignored) or export them in your shell.

## Layout

- `preferences.md`: candidate profile and tier definitions (`best`, `other`, `drop`) fed to the LLM filter.
- `src/job_radar/sources/__init__.py`: the company list, one line per company.
- `src/job_radar/sources/<system>.py`: one fetcher per hiring system (Greenhouse, Workday, Oracle, SuccessFactors, ...) or custom site (Porsche, Telekom, rinf.tech). Each returns `{id, title, company, location, url}` dicts.
- `src/job_radar/state.py`: Timișoara matching and result collection. `filter.py`: regex pre-filter and LLM tiering. `mailer.py`: the email. `runner.py`: one run.

## Changing companies

- Company on a known system: add one line to `FETCHERS`.
- New system: add `sources/<system>.py` with a `fetch(...)` and register the company.
- A company that fails during a run is noted at the bottom of that day's email (`<source> check broke: ...`).
- Pending: Haufe (its job board's search API rejects requests right now).
- Not tracked: Hella (its job list loads only through a session-token API; its site offers its own "Create an alert" emails), Cognizant, Infosys, SafeFleet (block scripted requests), Luxoft (no Timișoara roles listed).
