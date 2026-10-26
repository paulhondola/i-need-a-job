# i-need-a-job

Checks employers' careers APIs every 3 hours for Timișoara roles and emails the new ones (GitHub Actions, `.github/workflows/check.yml`).

- Run tests: `uv run pytest`
- Try it locally without sending or saving: `uv run job_radar.py --dry-run`
- Secrets: `SMTP_USER` (your Gmail address) and `SMTP_PASS` (a Gmail App Password).
- Add a company: write a `fetch_<name>()` returning `{id, title, company, location, url}` dicts and add it to `FETCHERS`. Its first run is silent.
- Changed a company's filter? Delete its key from `seen.json` in the same commit so it re-seeds silently.
- A company that starts failing gets one "check broke" email and one "recovered" email; it's listed under `broken` in `seen.json` meanwhile.
