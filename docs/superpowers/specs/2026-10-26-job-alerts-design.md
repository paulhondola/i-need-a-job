# i-need-a-job — design

Date: 2026-10-26

## Intent

Paul is job hunting in Timișoara. Several local employers post roles on their
own careers sites that never show up (or show up late) on LinkedIn. Checking
each site by hand is tedious and easy to forget. This project checks those
sites on a schedule and emails Paul when a job appears that they haven't been
told about before.

Success: Paul gets one email per run that found something, listing only the
new jobs, grouped by company, with a link to each. They never have to visit the
sites just to see if anything changed.

## Goals

- Watch these companies' careers sources for roles in Timișoara:
  Porsche (incl. MHP and other Porsche companies on the same board), OPSWAT,
  Nokia, Intel, Haufe.
- Detect *new* postings by job ID and email only those.
- Run unattended in the cloud every 3 hours, whether or not Paul's laptop is on.
- Make adding a company later a small, local change.
- Fail loudly but once: if a site changes and a fetcher breaks, Paul gets told
  when it breaks and when it recovers, not on every run in between.

## Non-goals

- Filtering by role, seniority or keyword. Paul explicitly wants all roles for
  now ("they aren't a lot and easy to filter visually").
- Tracking when jobs are removed, or keeping a history beyond what git gives.
- LinkedIn, Indeed or any aggregator.
- Any UI beyond the email. No other notification channels.

## Anti-goals (failure even if it "works")

- Re-alerting jobs Paul has already been told about (noise kills the tool).
- Emailing the entire current backlog on the first run.
- Silently doing nothing when a fetcher breaks.
- Credentials anywhere in the code or the repo history.
- The repo being public (it reveals who Paul is targeting).

## Decided by Paul

- Project/repo name: `i-need-a-job`.
- Runs as a GitHub Actions scheduled workflow (cloud), not on the laptop.
- Alerts by email, sent from Paul's own email account (Gmail) to themselves.
- Keep all roles; no filters.
- Location: **Timișoara** (not all of Romania).
- A source that returns zero jobs is not "broken"; only errors and unexpected
  response shapes are.
- Third-party libraries are fine: **httpx** for HTTP, **pytest** for tests,
  **uv** to manage and run them.

## Builder's calls already made (by Claude, not explicitly approved by Paul)

- **Python 3.12+ with uv.** A minimal `pyproject.toml` (not a package)
  declares `httpx` as the only runtime dependency and `pytest` in a `dev`
  dependency group; `uv.lock` is committed so the unattended job always runs
  the same versions. `uv run job_radar.py` and `uv run pytest` work the same
  locally and in CI. Everything else is stdlib (`json`, `smtplib`,
  `email.message`, `unicodedata`).
- **httpx** with a shared client: 30 s timeout, browser-like User-Agent,
  `follow_redirects=True`, `raise_for_status()` on every response.
- **Package** `src/job_radar/`, run as `python -m job_radar`; tests in
  `tests/` (layout changed by Paul's request after the first build, once the
  list of candidate companies grew to ~85).
- **One fetcher per hiring system** in `src/job_radar/sources/`
  (`greenhouse.py`, `workday.py`, `oracle.py`; custom sites like Porsche's get
  their own file), parameterized by company. The company list is
  `FETCHERS` in `sources/__init__.py`, one line per company. Every fetcher
  returns a list of dicts with the same shape:
  `{"id", "title", "company", "location", "url"}`. `id` is a string, unique
  within that source.
- **State** in `seen.json` at the repo root, committed back by the workflow:
  `{"seen": {"<source name>": ["<id>", ...], ...}, "broken": ["<source name>", ...]}`.
- **Location rule**, one shared helper used by every fetcher that filters
  client-side: keep a job if any of its locations contains `Timișoara` or
  `Timisoara` (case-insensitive), **or** is country-only `Romania` with no
  city. The second clause exists because Nokia (and possibly Intel/Haufe) list
  Romanian roles as just "Romania", and the employers on this list have their
  Romanian office in Timișoara. Remote roles count only if they name Timișoara.
- **Changing a source's filter later**: delete that source's key from
  `seen.seen` in the same commit, so the next run re-seeds it silently instead
  of emailing the newly matching backlog.
- **Broken sources notify once**: an email when a source starts failing and
  one when it recovers, tracked in `broken`. Source failures don't fail the
  GitHub run, so GitHub doesn't email on every run.
- **Seen IDs are a union that only grows** (never pruned). Keeps a job that
  briefly vanishes from an API and comes back from re-alerting. Growth is a
  few hundred IDs a year, negligible.
- **Per-source first run is silent**: if a source has no key in `seen.json`
  (first run ever, or a newly added company), record its current IDs and
  don't email them. This covers both "first run" and "added a company later".
- **Schedule**: every 3 hours (`0 */3 * * *`, UTC) plus `workflow_dispatch`
  for a manual "Run now" button.
- **Private** GitHub repo.
- **Email**: Gmail SMTP over SSL (`smtp.gmail.com:465`), auth with a Gmail
  App Password. From and To are both `SMTP_USER`. Secrets: `SMTP_USER`,
  `SMTP_PASS`. Plain-text body.
- **Tests**: one small pytest file covering the "what's new" logic
  (new vs seen, silent first run per source, union behavior, failed source
  keeps its old IDs, broken/recovered notified once) and the location rule.
  Fetchers are verified by running against the live sites, not mocked.

## Behavior

One run:

1. Load `seen.json` (missing file = `{"seen": {}, "broken": []}`).
2. Call every fetcher. Each source is independent: an exception (network
   error, HTTP error, unexpected JSON shape) in one is caught, recorded with
   its message, and the others still run. An empty list is a valid result.
3. For each source that succeeded:
   - If the source has no key in `seen`: store its IDs, report nothing.
   - Else: new = fetched jobs whose ID is not in `seen[source]`; add their
     IDs to `seen[source]`.
   - If the source was in `broken`: remove it, note "recovered".
4. For a source that failed: leave `seen[source]` untouched. If it wasn't in
   `broken`: add it, note "broke: <error>". If it already was: say nothing.
   Print the error to the run log either way.
5. If there are new jobs or broke/recovered notes, send one email:
   - Subject: `N new job(s): CompanyA, CompanyB` (or `job alert: Haufe check
     broke` when there are only notes).
   - Body grouped by company; per job: title, location, link. Broke/recovered
     notes at the bottom.
6. Write `seen.json` (stable formatting, sorted, so git diffs are readable).
7. Exit 0. Exit non-zero only for problems with the tool itself (SMTP failure,
   a bug outside a fetcher), so GitHub's own failure email means "the tool is
   down", not "one site is down".

Order matters: only save `seen.json` after the email was sent successfully, so
an SMTP failure doesn't swallow alerts. If sending fails, exit non-zero without
saving; the next run retries.

## Sources (verified 2026-10-26)

All of these were tested with plain HTTP requests (no browser) unless noted.

### Porsche — BeeSite JSON API

- `GET https://porsche-beesite-production-gjb.app.beesite.de/search/?data=<url-encoded JSON>`
- JSON:
  ```json
  {"LanguageCode":"EN",
   "SearchParameters":{"FirstItem":1,"CountItem":500,
     "MatchedObjectDescriptor":["ID","PositionTitle","PositionURI",
       "PositionLocation.CityName","ParentOrganizationName"]},
   "SearchCriteria":[
     {"CriterionName":"PositionLocation.Country","CriterionValue":["176"]},
     {"CriterionName":"PositionLocation.City","CriterionValue":["311"]},
     {"CriterionName":"PublicationChannel.Code","CriterionValue":["12"]}]}
  ```
  (176 = Romania, 311 = Timișoara, channel 12 = the public board; values taken
  from Paul's search URL.)
- Results: `SearchResult.SearchResultItems[].MatchedObjectDescriptor`.
  Total in `SearchResult.SearchResultCountAll` (26 on 2026-10-26).
- Company = `ParentOrganizationName` (e.g. "MHP - A Porsche Company",
  "Porsche Engineering Services GmbH"). Keep all of them.
- URL = `PositionURI` (e.g. `https://jobs.porsche.com/index.php?ac=jobad&id=20706`).

### OPSWAT — Greenhouse public board API

- `GET https://boards-api.greenhouse.io/v1/boards/opswat/jobs`
- `jobs[]` with `id`, `title`, `absolute_url`, `location.name`.
- `location.name` can list several places separated by `; `, e.g.
  `"Athina, Attica, Greece; Nicosia, Cyprus; Timișoara, Timiș, Romania"`.
  Keep a job if any part contains `Timișoara` or `Timisoara`. (7 such jobs on
  2026-10-26.)
- Note: `www.opswat.com` itself returns 403 to non-browser clients; the
  Greenhouse API does not.

### Nokia — Oracle Recruiting Cloud REST API

- `GET https://fa-evmr-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions`
  with query `onlyData=true`,
  `expand=requisitionList.secondaryLocations`,
  `finder=findReqs;siteNumber=CX_1,limit=200,offset=<n>,sortBy=POSTING_DATES_DESC`.
- Response: `items[0].requisitionList[]` (`Id`, `Title`, `PrimaryLocation`,
  `secondaryLocations`), total in `items[0].TotalJobsCount` (564 worldwide).
  Page with `offset` until all are fetched (3 requests today).
- Keyword search does **not** match locations, so fetch all and filter
  `PrimaryLocation` + secondary locations with the shared location rule.
  Nokia lists Romanian roles as just "Romania" (1 job on 2026-10-26), which
  the rule's country-only clause catches.
- URL: `https://jobs.nokia.com/en/sites/CX_1/job/<Id>` (builder: confirm this
  opens the job; adjust if not).

### Intel — Workday CXS API

- `POST https://intel.wd1.myworkdayjobs.com/wday/cxs/intel/External/jobs`
  body `{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}`.
- Location filtering via facets: the response's `facets` contains
  `locationMainGroup` → nested `locations` values, each with `descriptor`
  (e.g. `"Poland, Gdansk"`) and `id`. On 2026-10-26 there is **no Romania
  entry**, i.e. Intel has 0 Romanian roles.
- Fetcher: request once, look for location values whose descriptor passes the
  shared location rule (e.g. `Romania, Timisoara` or plain `Romania`).
  None → return `[]`. Otherwise re-query with
  `appliedFacets: {"locations": [<ids>]}`, paging by 20 via `offset` until
  `total` is reached.
- `jobPostings[]`: `title`, `externalPath`, `locationsText`. ID: the `JR…`
  requisition number (in `bulletFields` and at the end of `externalPath`).
  URL: `https://intel.wd1.myworkdayjobs.com/External` + `externalPath`.
- Since Romania currently yields nothing, the "Romania present" branch can't be
  tested live. That's acceptable; keep it simple and let it fail loudly if the
  shape is wrong when it eventually triggers.

### Haufe — talentsconnect job shop (riskiest source)

- Board: `https://jobs.haufegroup.com/en/search`. The server-rendered HTML says
  "42 / 42 jobs", but the job records aren't plain links in the HTML. They come
  from a Typesense search API (`https://api.my-job-shop.com/api/typesense/multi_search`)
  called with a scoped, **expiring** API key embedded in the page (the page has
  `typesenseApiKey…` and `typesenseUrl` in its Nuxt payload).
- Likely approach: fetch the page each run, extract the current key, then query
  Typesense for all jobs and filter with the shared location rule. The exact
  request body and field names still need to be found (watch the browser's
  network tab on that page).
- 0 Romanian roles on 2026-10-26.
- No other Haufe Timișoara source is known; use this main board.
- The expiring key makes this the source most likely to land in `broken`.
- **Build Haufe last.** If it takes disproportionate effort, ship the other four
  and leave Haufe as a follow-up; don't block the project on it.

## Workflow (`.github/workflows/check.yml`)

- Triggers: `schedule` (`0 */3 * * *`) and `workflow_dispatch`.
- `permissions: contents: write`.
- `concurrency` group so two runs never overlap and race on `seen.json`.
- Steps: checkout → setup-uv → `uv run --locked job_radar.py` with `SMTP_USER`/`SMTP_PASS` from
  secrets → commit and push `seen.json` only if it changed (bot identity,
  message like `seen: +N jobs`). Source failures exit 0 (see Behavior), so a
  plain sequential commit step is enough; if the script exits non-zero it
  saved nothing and there's nothing to commit.
- Scheduled workflows on a repo with no commits for 60 days get disabled by
  GitHub. `seen.json` commits will usually keep it alive; builder decides
  whether a keepalive is worth adding.
- Python via `astral-sh/setup-uv`; run steps use `uv run --locked ...` so a
  lockfile out of sync with `pyproject.toml` fails the run instead of
  silently resolving new versions.

## Setup steps that need Paul

- Create the private GitHub repo `i-need-a-job` and push. (Claude may do this
  with `gh` after Paul confirms.)
- Create a Gmail App Password (needs 2-step verification) and add the two repo
  secrets. Paul does this themselves; Claude never handles the password.
- Trigger "Run now" once to seed `seen.json` silently.

## Left to the builder

- Internal structure of `job_radar.py` beyond "one fetcher per source, common
  job shape".
- HTTP details: User-Agent, timeouts, retries (keep it minimal).
- Exact email wording and layout within the spec above.
- How to run things locally (e.g. a `--dry-run` that prints instead of
  emailing, if useful for checking fetchers).
