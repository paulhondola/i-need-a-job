# i-need-a-job (`job_radar`)

A stateless daily job radar that queries employers' careers APIs directly, filters and ranks matching roles with a regex + LLM pipeline, and emails a plain-text digest via GitHub Actions.

Out of the box, it watches **24 employers across Romania** (defaulting to **Timișoara**, configurable to any Romanian city, multiple cities, or all of Romania) for early-career software, AI, and data roles — and is structured so you can fork it and adapt it to your own profile, company list, or country.

## Features

- **Direct ATS APIs, no browser scraping** — talks to JSON/XML/RSS endpoints across 8 reusable ATS adapters (`Greenhouse`, `Lever`, `Oracle Recruiting Cloud`, `Personio`, `SAP SuccessFactors`, `SmartRecruiters`, `Teamtailor`, `Workday`) plus 3 custom career boards.
- **Flexible Romanian city filtering** — filter by one city, multiple cities (`timisoara,cluj`), or country-wide (`all` / `romania`), with built-in diacritic folding and aliases for 15 Romanian tech hubs plus automatic inclusion of Romania-remote roles.
- **Concurrent & fault-isolated** — fetches all 25 endpoints in parallel (`8` worker threads). If one board breaks, the others still deliver and the error is appended to the bottom of that day's email (`<source> check broke: ...`).
- **Stateless daily digest** — no database or state-commit churn; each run sends the current filtered openings and stays silent if nothing matches (and nothing broke).
- **Two-stage hybrid filtering** — a deterministic regex pre-filter removes obvious mismatches at zero token cost before an OpenAI-compatible LLM classifies surviving titles against [`preferences.md`](preferences.md) into `BEST MATCHES`, `OTHER TECH ROLES`, or dropped.
- **Graceful LLM fallback** — if `LLM_API_KEY` is missing or the provider errors/rate-limits, all regex-surviving jobs still arrive under `OTHER TECH ROLES` with an `llm filter broke: ...` note.
- **Zero-cost stack** — runs on GitHub Actions' free tier, any OpenAI-compatible free/cheap API (defaults to Groq), and Gmail SMTP. Minimal runtime footprint: Python ≥ 3.12, `httpx`, and `python-dotenv`.

## How It Works

```text
25 company endpoints (8 threads, filtered by CityFilter in cities.py)
  └─► per-source deduplication & error collection (state.py)
        └─► regex pre-filter: drop senior/non-tech/German titles (filter.py)
              └─► LLM tiering in chunks of 200 using preferences.md (filter.py)
                    └─► plain-text tiered digest via Gmail SMTP / --dry-run (mailer.py)
```

### Example Digest Email

```text
Subject: [Timișoara] 2 best, 1 other jobs: Bosch, Nokia, OPSWAT

=== BEST MATCHES (2) ===

Nokia
- Python Software Engineer Intern (Timisoara, Romania)
  https://jobs.nokia.com/en/sites/CX_1/job/12345

OPSWAT
- Junior Backend Engineer (Timisoara, Romania)
  https://boards.greenhouse.io/opswat/jobs/67890

=== OTHER TECH ROLES (1) ===

Bosch
- Embedded C++ Developer (Timișoara, Romania)
  https://jobs.smartrecruiters.com/BoschGroup/abc123
```

The subject prefix reflects the active city filter (e.g. `[Timișoara]`, `[Timișoara, Cluj-Napoca]`, or `[Romania]`). If a board or the LLM fails during a run, a plain-text error line is appended at the bottom instead of aborting the digest.

## Quick Start (Personal Setup)

### 1. Try it locally (`--dry-run`)

Requires Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/<your-username>/i-need-a-job.git
cd i-need-a-job
cp .env.example .env
```

Edit `.env` and add `LLM_API_KEY` (or leave it unset to see the regex-only fallback), then run a dry run that prints the digest to stdout without sending email:

```bash
# Default (Timișoara + Romania-remote)
uv run python -m job_radar --dry-run

# Specific Romanian cities (comma-separated or repeated --city flags)
uv run python -m job_radar --dry-run --city timisoara,cluj
uv run python -m job_radar --dry-run --city bucharest --city iasi

# All of Romania ("all" or "romania")
uv run python -m job_radar --dry-run --city all
```

### 2. Enable daily emails with GitHub Actions

1. **Fork this repository** to your GitHub account.
2. **Create a Gmail App Password** (your regular password will not work):
   - Turn on **2-Step Verification** in your Google Account security settings.
   - Open [Google App Passwords](https://myaccount.google.com/apppasswords), create a password for "Mail", and copy the 16-character value.
3. **Add repository Secrets and Variables** in **Settings → Secrets and variables → Actions** (note that credentials go under **Secrets**, while city and provider overrides go under **Variables**):

| Name | GitHub Actions Tab | Required | Default | Purpose |
| --- | --- | --- | --- | --- |
| `SMTP_USER` | Secret | Yes (for email) | — | Gmail address used as both `From` and `To` |
| `SMTP_PASS` | Secret | Yes (for email) | — | Gmail App Password |
| `LLM_API_KEY` | Secret | Recommended | — | Bearer token for the LLM API (falls back to regex-only if unset) |
| `CITIES` | Variable | No | `Timișoara` | Comma-separated Romanian cities (e.g. `timisoara,cluj`) or `all` *(GitHub Actions only; locally use `--city`)* |
| `LLM_BASE_URL` | Variable | No | `https://api.groq.com/openai/v1` | OpenAI-compatible API base URL |
| `LLM_MODEL` | Variable | No | `openai/gpt-oss-120b` | Model name sent to `/chat/completions` |

4. **Test the workflow**: open **Actions → `check jobs` → Run workflow** (you can optionally enter a `city` input to override `CITIES` for that single run). Once enabled on your fork, GitHub Actions runs daily at `08:00 UTC` (and runs `pytest` before each fetch).

### Using a Different LLM Provider

Any OpenAI-compatible `/chat/completions` endpoint that supports `response_format: {"type": "json_object"}` works. Set `LLM_API_KEY` plus `LLM_BASE_URL` and `LLM_MODEL`:

```dotenv
# Groq (default — free tier; jobs are batched in chunks of 200 to stay under 12k TPM)
LLM_API_KEY=gsk_...

# OpenAI
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...

# OpenRouter
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openai/gpt-4o-mini
LLM_API_KEY=sk-or-...

# Local Ollama (local runs only)
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:14b
LLM_API_KEY=ollama
```

## Customizing for Your Own Job Search

### 1. Pick your city or cities (Romania — no code changes needed)

- **Locally:** pass `--city` (comma-separated or repeated), e.g. `--city bucharest,cluj` or `--city all`.
- **GitHub Actions:** set the `CITIES` repository variable (e.g. `cluj,brasov` or `all`), or pass a one-off `city` value when triggering `workflow_dispatch`.

Built-in hub catalog in [`src/job_radar/cities.py`](src/job_radar/cities.py) handles diacritics and aliases for 15 cities (`Timișoara`, `Bucharest`/`Bucuresti`, `Cluj-Napoca`/`Cluj`, `Iași`, `Brașov`, `Sibiu`, `Oradea`, `Craiova`, `Constanța`, `Arad`, `Ploiești`, `Târgu Mureș`/`Tg. Mureș`, `Pitești`, `Galați`, `Bacău`), and falls back cleanly for unlisted city names. Country-only `"Romania"` and Romania-remote listings are automatically included alongside selected cities.

### 2. Edit your candidate profile & tiers

Replace [`preferences.md`](preferences.md) with your own background, tech stack, and definitions for `best`, `other`, and dropped roles. The entire file is sent as the LLM system prompt.

### 3. Check the regex pre-filter (important!)

[`_DROP_RE`](src/job_radar/filter.py) in `src/job_radar/filter.py` runs **before** the LLM ever sees a title. It currently drops:
- Seniority terms (`senior`, `sr`, `lead`, `principal`, `staff`, `architect`, `manager`, `director`, `head of`, `vp`, `chief`, `expert`)
- Non-engineering departments (HR, finance/accounting, procurement, legal, sales/marketing, logistics/warehouse, mechanical/manufacturing/plant)
- Titles explicitly requiring German (`german speaker`, `with german`, `german language`)

If you are targeting Senior/Lead roles, speak German, or want non-SWE roles, edit or remove those patterns in [`src/job_radar/filter.py`](src/job_radar/filter.py) (and update `tests/test_filter.py` to match) — editing `preferences.md` alone will not recover roles dropped by `_DROP_RE`.

### 4. Add or remove companies

Tracked companies live in `FETCHERS` inside [`src/job_radar/sources/__init__.py`](src/job_radar/sources/__init__.py).

- **Company on a supported ATS:** add one `partial(...)` entry to `FETCHERS`:

| Adapter (`src/job_radar/sources/`) | Required arguments | Example |
| --- | --- | --- |
| `greenhouse.fetch` | `board`, `company` | `partial(greenhouse.fetch, board="opswat", company="OPSWAT")` |
| `lever.fetch` | `slug`, `company` *(opt: `api_host="api.eu.lever.co"`)* | `partial(lever.fetch, slug="everseen", company="Everseen", api_host="api.eu.lever.co")` |
| `oracle.fetch` | `api_host`, `site`, `job_url_prefix`, `company` | `partial(oracle.fetch, api_host="...", site="CX_1", job_url_prefix="...", company="Nokia")` |
| `personio.fetch` | `slug`, `company` *(opt: `tld`, `job_url`)* | `partial(personio.fetch, slug="manage-now", company="Manage Now")` |
| `smartrecruiters.fetch` | `slug`, `company` | `partial(smartrecruiters.fetch, slug="endava", company="Endava")` |
| `successfactors.fetch` | `host`, `company` | `partial(successfactors.fetch, host="jobs.atos.net", company="Atos")` |
| `teamtailor.fetch` | `slug`, `company` | `partial(teamtailor.fetch, slug="vismacc", company="Visma")` |
| `workday.fetch` | `host`, `tenant`, `site`, `company` | `partial(workday.fetch, host="intel.wd1.myworkdayjobs.com", tenant="intel", site="External", company="Intel")` |

- **New hiring system or custom site:** add `src/job_radar/sources/<system>.py` exposing `fetch(..., city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]` returning dicts with keys `{"id", "title", "company", "location", "url"}`, then register it in `FETCHERS`.

### 5. Target a different country (outside Romania)

Any Romanian city works without code edits. To adapt the repo to another country:

1. **City catalog & country matching:** update `ROMANIAN_CITIES`, `DEFAULT_CITY_FILTER`, and the `Romania`/`RO` checks in [`src/job_radar/cities.py`](src/job_radar/cities.py).
2. **Country-scoped API queries in 4 fetchers:** update or remove the Romania query parameters in:
   - [`src/job_radar/sources/smartrecruiters.py`](src/job_radar/sources/smartrecruiters.py) (`country="ro"`)
   - [`src/job_radar/sources/beesite.py`](src/job_radar/sources/beesite.py) (Porsche `Country=176`)
   - [`src/job_radar/sources/telekom.py`](src/job_radar/sources/telekom.py) (`location="Romania"`)
   - [`src/job_radar/sources/rinf.py`](src/job_radar/sources/rinf.py) (`country="Romania"` when `--city all`)

The other 7 adapters (`greenhouse`, `lever`, `oracle`, `personio`, `successfactors`, `teamtailor`, `workday`) are already driven purely by `CityFilter`.

### 6. Change schedule or email delivery

- **Schedule:** edit the `cron` expression in [`.github/workflows/check.yml`](.github/workflows/check.yml) (default `0 8 * * *` = 08:00 UTC daily).
- **SMTP host or recipient:** `send_email()` in [`src/job_radar/mailer.py`](src/job_radar/mailer.py) connects to `smtp.gmail.com:465` and sends from `SMTP_USER` to `SMTP_USER`. Edit that function if you use another SMTP server or want a separate recipient address.

## Tracked Companies (Default List)

<details>
<summary>24 companies / 25 endpoints currently configured (click to expand)</summary>

| Company | Adapter | Notes |
| --- | --- | --- |
| Accenture | `workday` | |
| ACI Worldwide | `oracle` | |
| Atos | `successfactors` | |
| Aumovio | `smartrecruiters` | |
| Bosch | `smartrecruiters` | |
| d.velop | `personio` | Links to listings page (site uses title slugs) |
| Deutsche Telekom | `telekom` | Custom Eightfold search proxy |
| DRÄXLMAIER | `successfactors` | |
| Endava | `smartrecruiters` | |
| Everseen | `lever` | EU Lever host (`api.eu.lever.co`) |
| EY | `successfactors` | |
| Huf | `successfactors` | |
| Intel | `workday` | |
| Manage Now | `personio` | |
| Nagarro | `smartrecruiters` | |
| Nokia | `oracle` | |
| NTT DATA | `successfactors` | |
| OPSWAT | `greenhouse` | |
| Porsche | `beesite` | Custom Beesite search API |
| rinf.tech | `rinf` | Custom HTML board parser |
| SAP | `smartrecruiters` + `successfactors` | Tracked on both new and legacy sites during migration |
| Schaeffler | `successfactors` | |
| TE Connectivity | `successfactors` | |
| Visma | `teamtailor` | |

- **Pending:** Haufe (its job board search API currently rejects requests).
- **Not tracked:** Hella (session-token-gated API; offers its own email alerts), Cognizant / Infosys / SafeFleet (block scripted requests), Luxoft (no Timișoara roles listed).

</details>

## Project Layout

```text
.
├── .env.example                 # Local environment variable template
├── .github/workflows/check.yml  # Daily GitHub Actions job (tests + digest)
├── preferences.md               # Candidate profile & LLM classification rules
├── lefthook.yml                 # Pre-commit hooks (ruff, pyrefly, pytest)
├── src/job_radar/
│   ├── __main__.py              # CLI entry point (`python -m job_radar`)
│   ├── runner.py                # CLI (`--dry-run`, `--city`) & concurrent run orchestration
│   ├── cities.py                # Romanian city catalog, alias/diacritic folding & CityFilter
│   ├── client.py                # Shared httpx.Client
│   ├── state.py                 # Per-source deduplication & error note collection
│   ├── filter.py                # Regex pre-filter & OpenAI-compatible LLM tiering
│   ├── mailer.py                # Tiered plain-text formatting & Gmail SMTP
│   └── sources/                 # Company registry (__init__.py) + 11 ATS/site fetchers
└── tests/                       # Offline unit tests
```

## Development

All tests run completely offline (no live HTTP or LLM calls):

```bash
uv run pytest                         # Run unit tests
uv run ruff check                     # Lint
uv run ruff format --check src tests  # Check formatting
uv run pyrefly check                  # Static type check
```

If you use [Lefthook](https://github.com/evilmartians/lefthook), `lefthook install` wires up the pre-commit pipeline defined in [`lefthook.yml`](lefthook.yml) (`ruff`, `pyrefly`, and `pytest`).
