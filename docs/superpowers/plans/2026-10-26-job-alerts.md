# i-need-a-job Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A GitHub Actions job that checks five employers' careers APIs every 3 hours for Timișoara roles and emails only the new ones.

**Architecture:** One Python script, `job_radar.py`: one fetcher per source returning a common job shape, a pure `update_state` that diffs against `seen.json`, an email formatter, and a `run()` that wires them with injected fetchers and sender so it's testable. A workflow runs it on cron and commits `seen.json` back.

**Tech Stack:** Python 3.12+, uv (deps + lockfile + runner), httpx (HTTP), pytest (tests), stdlib for the rest (`json`, `smtplib`, `email.message`, `unicodedata`), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-26-job-alerts-design.md`. Endpoints, request bodies and response field names for every source are there; this plan does not repeat them.

## Global Constraints

- Dependencies: runtime `httpx` only; `pytest` in the `dev` dependency group. Nothing else without a reason in the commit message.
- `pyproject.toml` with `[tool.uv] package = false`; `uv.lock` committed. Run everything through uv: `uv run pytest`, `uv run job_radar.py`.
- All code in `job_radar.py` at the repo root; tests in `test_job_radar.py` at the repo root.
- Job shape: `{"id": str, "title": str, "company": str, "location": str, "url": str}`. `id` always `str`.
- Source names (keys in `seen.json`, used in notes): `Porsche`, `OPSWAT`, `Nokia`, `Intel`, `Haufe`.
- State file `seen.json`: `{"seen": {"<source>": ["<id>", ...]}, "broken": ["<source>", ...]}`, written with `indent=2`, `sort_keys=True`, `ensure_ascii=False`, ID lists sorted, trailing newline.
- HTTP: one shared `httpx.Client(timeout=30, headers={"User-Agent": <browser-like>}, follow_redirects=True)`; call `.raise_for_status()` on every response.
- Email: `smtplib.SMTP_SSL("smtp.gmail.com", 465)`, login with env `SMTP_USER` / `SMTP_PASS`, From = To = `SMTP_USER`, plain text.
- Never put credentials in code, tests, commits or logs.

## Review Focus

1. **Romanian diacritic variants**: sites write `Timișoara` (comma ș, U+0219), `Timişoara` (cedilla ş, U+015F), `Timisoara`, any case. All must match. Pinned in Task 1.
2. **Integer IDs**: Greenhouse returns `id` as an int. If an int ever reaches the state, a job re-alerts every run forever. `update_state` coerces IDs to `str`. Pinned in Task 1.
3. **Duplicate IDs within one fetch**: paging an API while it changes can return the same job twice. It must be one alert, not two. Pinned in Task 1.
4. **"Romania" with another city** (`Romania, Bucharest`, `Cluj-Napoca, Romania`) must *not* match; only country-only `Romania` or a Timișoara mention. Pinned in Task 1.
5. **A hanging site**: one stalled request must not hold the run for GitHub's 6-hour default. 30 s client timeout (Global Constraints) plus `timeout-minutes: 10` on the workflow job (Task 6).

---

### Task 1: Project setup, location rule, state diff

**Files:**
- Create: `pyproject.toml`, `uv.lock` (generated), `.gitignore`, `job_radar.py`, `test_job_radar.py`

**Interfaces:**
- Produces:
  - `matches_timisoara(location: str) -> bool`
  - `update_state(state: dict, results: dict[str, list[dict] | Exception]) -> tuple[dict, dict[str, list[dict]], list[str]]`: returns `(new_state, new_jobs_by_source, notes)`. Does not mutate `state`.

- [ ] **Step 1: Init git and the uv project**

```toml
# pyproject.toml
[project]
name = "i-need-a-job"
version = "0"
requires-python = ">=3.12"
dependencies = ["httpx"]

[dependency-groups]
dev = ["pytest"]

[tool.uv]
package = false
```

`.gitignore`: `__pycache__/`, `.venv/`, `.pytest_cache/`.

Run: `git init && git branch -M main && uv lock`
Expected: `Initialized empty Git repository`, then `Resolved N packages`; `uv.lock` exists.

- [ ] **Step 2: Write failing tests in `test_job_radar.py`**

```python
import pytest
from job_radar import matches_timisoara, update_state

def job(id, company="X"):
    return {"id": id, "title": f"T{id}", "company": company, "location": "Timișoara", "url": f"u{id}"}

EMPTY = {"seen": {}, "broken": []}

@pytest.mark.parametrize("loc", ["Timișoara", "Timişoara", "Timisoara", "TIMISOARA",
    "Timișoara, Timiș, Romania", "Romania, Timisoara", "Romania", " romania "])
def test_location_matches(loc):
    assert matches_timisoara(loc)

@pytest.mark.parametrize("loc", ["Romania, Bucharest", "Cluj-Napoca, Romania",
    "Budapest, Hungary", "EMEA - Remote", ""])
def test_location_rejects(loc):
    assert not matches_timisoara(loc)

def test_first_run_for_source_is_silent():
    state, new, notes = update_state(EMPTY, {"OPSWAT": [job("1"), job("2")]})
    assert new == {}
    assert state["seen"]["OPSWAT"] == ["1", "2"]

def test_reports_only_unseen():
    state, new, _ = update_state({"seen": {"OPSWAT": ["1"]}, "broken": []}, {"OPSWAT": [job("1"), job("2")]})
    assert [j["id"] for j in new["OPSWAT"]] == ["2"]
    assert state["seen"]["OPSWAT"] == ["1", "2"]

def test_seen_is_a_growing_union():
    state, new, _ = update_state({"seen": {"OPSWAT": ["1", "2"]}, "broken": []}, {"OPSWAT": [job("2")]})
    assert new == {}
    assert state["seen"]["OPSWAT"] == ["1", "2"]

def test_int_ids_match_str_seen():
    state, new, _ = update_state({"seen": {"OPSWAT": ["4738830005"]}, "broken": []}, {"OPSWAT": [job(4738830005)]})
    assert new == {}
    assert state["seen"]["OPSWAT"] == ["4738830005"]

def test_duplicate_ids_in_one_fetch_alert_once():
    _, new, _ = update_state({"seen": {"Nokia": []}, "broken": []}, {"Nokia": [job("7"), job("7")]})
    assert len(new["Nokia"]) == 1

def test_failure_keeps_seen_and_notes_once():
    state, _, notes = update_state({"seen": {"Haufe": ["1"]}, "broken": []}, {"Haufe": RuntimeError("key expired")})
    assert state["seen"]["Haufe"] == ["1"]
    assert state["broken"] == ["Haufe"]
    assert notes == ["Haufe check broke: key expired"]
    state2, _, notes2 = update_state(state, {"Haufe": RuntimeError("key expired")})
    assert notes2 == []
    assert state2["broken"] == ["Haufe"]

def test_recovery_noted_once():
    state, _, notes = update_state({"seen": {"Haufe": ["1"]}, "broken": ["Haufe"]}, {"Haufe": [job("1")]})
    assert state["broken"] == []
    assert notes == ["Haufe check recovered"]

def test_empty_result_is_not_broken():
    state, _, notes = update_state({"seen": {"Intel": []}, "broken": []}, {"Intel": []})
    assert (state["broken"], notes) == ([], [])

def test_does_not_mutate_input():
    s = {"seen": {"OPSWAT": ["1"]}, "broken": []}
    update_state(s, {"OPSWAT": [job("2")], "Haufe": RuntimeError("x")})
    assert s == {"seen": {"OPSWAT": ["1"]}, "broken": []}
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `uv run pytest -q`
Expected: collection error, `ImportError: cannot import name 'matches_timisoara'`

- [ ] **Step 4: Implement both functions in `job_radar.py`**

`matches_timisoara`: normalize with `unicodedata.normalize("NFKD", s)`, drop combining marks, `casefold()`, `strip()`. Match if the result contains `timisoara`, or equals `romania`. (NFKD splits both ș and ş into `s` plus a combining mark, so one rule covers both.)

`update_state`: deep-copy the input (`copy.deepcopy`). Note strings are exactly `"<source> check broke: <str(exc)>"` and `"<source> check recovered"`. Keep stored ID lists sorted.

- [ ] **Step 5: Run tests, verify they pass**

Run: `uv run pytest -q`
Expected: `22 passed`

- [ ] **Step 6: Commit**

```bash
git add .gitignore pyproject.toml uv.lock job_radar.py test_job_radar.py docs/
git commit -m "feat: location rule and seen-state diff"
```

---

### Task 2: Email formatting and sending

**Files:**
- Modify: `job_radar.py`, `test_job_radar.py`

**Interfaces:**
- Consumes: `new_jobs_by_source`, `notes` shapes from Task 1.
- Produces:
  - `format_email(new_jobs: dict[str, list[dict]], notes: list[str]) -> tuple[str, str] | None`: `None` when there is nothing to say.
  - `send_email(subject: str, body: str) -> None`

- [ ] **Step 1: Write failing tests**

```python
from job_radar import format_email

def test_email_nothing_to_say():
    assert format_email({}, []) is None

def test_email_groups_by_company_not_source():
    new = {"Porsche": [job("1", "MHP - A Porsche Company"), job("2", "Porsche Engineering Services GmbH")],
           "OPSWAT": [job("3", "OPSWAT")]}
    subject, body = format_email(new, [])
    assert subject == "3 new jobs: MHP - A Porsche Company, OPSWAT, Porsche Engineering Services GmbH"
    for s in ["T1", "T2", "T3", "u1", "u3", "Timișoara"]:
        assert s in body
    assert body.index("MHP") < body.index("T1")

def test_email_singular():
    subject, _ = format_email({"OPSWAT": [job("3", "OPSWAT")]}, [])
    assert subject == "1 new job: OPSWAT"

def test_email_notes_only():
    subject, body = format_email({}, ["Haufe check broke: boom"])
    assert subject == "job alert: Haufe check broke: boom"
    assert "Haufe check broke: boom" in body

def test_email_notes_after_jobs():
    _, body = format_email({"OPSWAT": [job("3", "OPSWAT")]}, ["Intel check recovered"])
    assert body.index("T3") < body.index("Intel check recovered")
```

- [ ] **Step 2: Run tests, verify the new ones fail**

Run: `uv run pytest -q`
Expected: `ImportError: cannot import name 'format_email'`

- [ ] **Step 3: Implement `format_email` and `send_email`**

`format_email`: companies sorted alphabetically in subject and body. Notes-only subject is `"job alert: " + "; ".join(notes)`. One block per company: company name line, then per job `- {title} ({location})` and the URL on the next line.

`send_email`: build an `email.message.EmailMessage` (handles UTF-8 titles), send via the Global Constraints SMTP settings. Not unit-tested; verified live in Task 6.

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest -q`
Expected: `27 passed`

- [ ] **Step 5: Commit**

```bash
git add job_radar.py test_job_radar.py
git commit -m "feat: alert email formatting and SMTP send"
```

---

### Task 3: `run()` orchestration and CLI

**Files:**
- Modify: `job_radar.py`, `test_job_radar.py`

**Interfaces:**
- Consumes: `update_state`, `format_email`, `send_email`.
- Produces:
  - `run(fetchers: dict[str, Callable[[], list[dict]]], state_path: pathlib.Path, send: Callable[[str, str], None], save: bool = True) -> int`: exit code.
  - `FETCHERS: dict[str, Callable[[], list[dict]]]`: starts empty; Tasks 4–5 register into it.
  - `main() -> int`, run via `if __name__ == "__main__": sys.exit(main())`; `--dry-run` sends to `print` and passes `save=False`.

- [ ] **Step 1: Write failing tests** (pytest's `tmp_path` fixture)

```python
import json
from job_radar import run

def boom():
    raise RuntimeError("down")

def test_run_missing_state_seeds_silently(tmp_path):
    path, sent = tmp_path / "seen.json", []
    assert run({"OPSWAT": lambda: [job("1")]}, path, lambda s, b: sent.append(s)) == 0
    assert sent == []
    assert json.loads(path.read_text()) == {"seen": {"OPSWAT": ["1"]}, "broken": []}

def test_run_new_job_emails_and_saves(tmp_path):
    path, sent = tmp_path / "seen.json", []
    path.write_text(json.dumps({"seen": {"OPSWAT": ["1"]}, "broken": []}))
    assert run({"OPSWAT": lambda: [job("1"), job("2", "OPSWAT")]}, path, lambda s, b: sent.append(s)) == 0
    assert sent == ["1 new job: OPSWAT"]
    assert "2" in json.loads(path.read_text())["seen"]["OPSWAT"]

def test_run_one_source_raising_does_not_stop_others(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text(json.dumps({"seen": {"OPSWAT": [], "Haufe": []}, "broken": []}))
    assert run({"Haufe": boom, "OPSWAT": lambda: [job("2", "OPSWAT")]}, path, lambda s, b: None) == 0
    state = json.loads(path.read_text())
    assert state["broken"] == ["Haufe"]
    assert state["seen"]["OPSWAT"] == ["2"]

def test_run_smtp_failure_saves_nothing_and_exits_nonzero(tmp_path):
    path = tmp_path / "seen.json"
    before = {"seen": {"OPSWAT": ["1"]}, "broken": []}
    path.write_text(json.dumps(before))
    def bad_send(s, b):
        raise OSError("smtp down")
    assert run({"OPSWAT": lambda: [job("2")]}, path, bad_send) != 0
    assert json.loads(path.read_text()) == before

def test_run_dry_run_does_not_save(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text(json.dumps({"seen": {"OPSWAT": ["1"]}, "broken": []}))
    run({"OPSWAT": lambda: [job("2")]}, path, lambda s, b: None, save=False)
    assert json.loads(path.read_text())["seen"]["OPSWAT"] == ["1"]

def test_run_state_file_format(tmp_path):
    path = tmp_path / "seen.json"
    run({"OPSWAT": lambda: [job("b"), job("a")]}, path, lambda s, b: None)
    text = path.read_text()
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
```

- [ ] **Step 2: Run tests, verify the new ones fail**

Run: `uv run pytest -q`
Expected: `ImportError: cannot import name 'run'`

- [ ] **Step 3: Implement `run`, `FETCHERS`, `main`**

`run` catches `Exception` around each fetcher only (prints `"<source>: <error>"` to stderr) and passes it to `update_state`. If `send` raises, print the error and return 1 without saving. Otherwise save (when `save`) and return 0. Print a one-line summary per source (count fetched, count new) for the Actions log. State path in `main` is `Path(__file__).with_name("seen.json")`.

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest -q`
Expected: `33 passed`

- [ ] **Step 5: Commit**

```bash
git add job_radar.py test_job_radar.py
git commit -m "feat: run orchestration with per-source isolation and dry run"
```

---

### Task 4: Porsche, OPSWAT, Nokia fetchers

All three were verified live on 2026-10-26; follow the spec's Sources section exactly for URLs, request bodies and field names.

**Files:**
- Modify: `job_radar.py`

**Interfaces:**
- Consumes: `matches_timisoara`, `FETCHERS`.
- Produces:
  - `HTTP: httpx.Client`: module-level shared client configured per Global Constraints.
  - `fetch_porsche() -> list[dict]`, `fetch_opswat() -> list[dict]`, `fetch_nokia() -> list[dict]`, registered as `FETCHERS["Porsche"|"OPSWAT"|"Nokia"]`.

- [ ] **Step 1: Add `HTTP` and implement `fetch_porsche`**

`HTTP.get(url, params={"data": json.dumps(query)})`. Filtering is server-side (country 176, city 311, channel 12), `CountItem` 500. `company` = `ParentOrganizationName`. `location` = first `PositionLocation[].CityName`. `url` = `PositionURI`.

- [ ] **Step 2: Verify Porsche live**

Run: `uv run python -c "import job_radar as j; r=j.fetch_porsche(); print(len(r)); print(r[0])"`
Expected: a count ≥ 1 (26 on 2026-10-26) and a dict with all five keys, all `str`, `url` starting `https://jobs.porsche.com/index.php?ac=jobad&id=`.

- [ ] **Step 3: Implement `fetch_opswat`**

Keep a job if any `"; "`-separated part of `location.name` passes `matches_timisoara`. `company` = `"OPSWAT"`. `id` = `str(id)`. `url` = `absolute_url`.

- [ ] **Step 4: Verify OPSWAT live**

Run: `uv run python -c "import job_radar as j; r=j.fetch_opswat(); print(len(r)); [print(x['id'], x['title'], '|', x['location']) for x in r]"`
Expected: ≥ 1 jobs (7 on 2026-10-26), every location mentioning Timișoara, none purely elsewhere.

- [ ] **Step 5: Implement `fetch_nokia`**

Pass the `finder` value as a normal entry in `params` (httpx percent-encodes `;`, `,` and `=`, and Oracle accepts that; verified 2026-10-26). Page with `offset` in steps of 200 until `TotalJobsCount` is reached, or stop early if a page returns no rows. Filter `PrimaryLocation` and each secondary location's name with `matches_timisoara`. `company` = `"Nokia"`. `url` = `https://jobs.nokia.com/en/sites/CX_1/job/<Id>`.

- [ ] **Step 6: Verify Nokia live, including the job URL**

Run: `uv run python -c "import job_radar as j; r=j.fetch_nokia(); print(len(r)); print(r)"`
Expected: ≥ 0 jobs without error (1 on 2026-10-26, location `Romania`). Open one printed `url` in a browser: it must show that job. If it doesn't, find the right pattern from the jobs.nokia.com UI and fix it.

- [ ] **Step 7: Dry run end to end**

Run: `uv run job_radar.py --dry-run`
Expected: summary lines for Porsche, OPSWAT, Nokia; no email printed (first run seeds silently); no `seen.json` created.

- [ ] **Step 8: Commit**

```bash
git add job_radar.py
git commit -m "feat: Porsche, OPSWAT and Nokia fetchers"
```

---

### Task 5: Intel and Haufe fetchers

**Files:**
- Modify: `job_radar.py`

**Interfaces:**
- Consumes: `HTTP`, `matches_timisoara`, `FETCHERS`.
- Produces: `fetch_intel() -> list[dict]`, `fetch_haufe() -> list[dict]`, registered as `FETCHERS["Intel"|"Haufe"]`.

- [ ] **Step 1: Implement `fetch_intel`**

Facet approach per the spec, using `HTTP.post(url, json=body)`: first request, collect `id`s of `locationMainGroup` → `locations` values whose `descriptor` passes `matches_timisoara`. None → `[]`. Else re-POST with `appliedFacets: {"locations": ids}` and page by 20. `id` = the `JR…` number taken from the end of `externalPath`. `company` = `"Intel"`. `location` = `locationsText`. `url` = `https://intel.wd1.myworkdayjobs.com/External` + `externalPath`. If `locationMainGroup` or `locations` is missing from the response, raise (shape changed), don't return `[]`.

- [ ] **Step 2: Verify Intel live**

Run: `uv run python -c "import job_radar as j; print(j.fetch_intel())"`
Expected: `[]` on 2026-10-26, no exception.

- [ ] **Step 3: Discover Haufe's Typesense request**

Open `https://jobs.haufegroup.com/en/search` in a browser with devtools. Record the `multi_search` request: how the page supplies the key (it was in the URL query as `x-typesense-api-key`; the value also appears in the page's Nuxt payload near `typesenseApiKey`), the POST body (collection name, `q`, `filter_by`, `per_page`, page), and the job fields for id, title, location and URL slug. Confirm the same request works from a plain `httpx` call with a key scraped from a fresh page fetch.
Expected: a request returning all ~42 jobs as JSON. **If this takes more than about an hour, stop:** skip Steps 4–5, leave Haufe out of `FETCHERS`, and note it as a follow-up in the final report.

- [ ] **Step 4: Implement `fetch_haufe`**

Each call fetches the page, extracts the current key and Typesense URL, queries all jobs (page through if needed) and filters with `matches_timisoara`. `company` = `"Haufe"`. Raise if the key can't be found in the page.

- [ ] **Step 5: Verify Haufe live**

Run: `uv run python -c "import job_radar as j; r=j.fetch_haufe(); print(len(r), r[:2])"`
Expected: no exception; `0` on 2026-10-26. Also temporarily print the unfiltered count once: about 42.

- [ ] **Step 6: Dry run, tests, commit**

Run: `uv run job_radar.py --dry-run && uv run pytest -q`
Expected: summary lines for all registered sources, no email, `33 passed`.

```bash
git add job_radar.py
git commit -m "feat: Intel and Haufe fetchers"
```

---

### Task 6: Workflow, GitHub repo, first live run

**Files:**
- Create: `.github/workflows/check.yml`, `README.md` (5–10 lines: what it does, `uv run pytest` / `uv run job_radar.py --dry-run`, the two secrets, how to add a company, how to re-seed a source by deleting its key from `seen.json`)

**Interfaces:**
- Consumes: `uv run job_radar.py` (exit 0 = fine, non-zero = tool down).

- [ ] **Step 1: Write `.github/workflows/check.yml`**

```yaml
name: check jobs
on:
  schedule: [{ cron: "0 */3 * * *" }]
  workflow_dispatch:
concurrency: { group: check-jobs, cancel-in-progress: false }
permissions: { contents: write }
jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv run --locked pytest -q
      - run: uv run --locked job_radar.py
        env:
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
      - name: commit seen.json
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add seen.json
          git diff --cached --quiet || { git commit -m "seen: update" && git push; }
```

- [ ] **Step 2: Commit locally**

```bash
git add .github README.md
git commit -m "ci: scheduled job check workflow"
```

- [ ] **Step 3: Create the private repo and push (ask Paul first: this publishes to GitHub)**

Run: `gh repo create i-need-a-job --private --source . --push`
Expected: repo URL printed; `gh repo view --json visibility` shows `PRIVATE`.

- [ ] **Step 4: Paul adds secrets (Claude does not handle the password)**

Paul creates a Gmail App Password and runs `gh secret set SMTP_USER` and `gh secret set SMTP_PASS` (interactive prompts), or uses repo Settings → Secrets.
Expected: `gh secret list` shows both names.

- [ ] **Step 5: First run seeds silently**

Run: `gh workflow run "check jobs"`, then `gh run list --workflow "check jobs" --limit 1` to get the run ID, then `gh run watch <id> --exit-status`.
Expected: green run, no email, a `seen: update` commit containing every source's current IDs.

- [ ] **Step 6: Prove an alert arrives**

Remove one OPSWAT ID from `seen.json`, commit, push, then trigger the workflow again.
Expected: green run; Paul receives `1 new job: OPSWAT` in their inbox with a working link; the ID is back in `seen.json`.
