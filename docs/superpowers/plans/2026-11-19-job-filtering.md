# Job Filtering & Preference Tiering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filter daily Timișoara job postings with a fast regex drop-list and tier the survivors into Best Matches vs. Other Tech Roles using an OpenAI-compatible LLM (defaulting to Groq `llama-3.3-70b-versatile`) guided by `preferences.md`.

**Architecture:** A new `src/job_radar/filter.py` module sits between `collect_results()` and `format_email()`: `regex_prefilter()` strips obvious senior, non-tech, and German-fluency titles, then `llm_filter()` sends surviving titles in numbered chunks of ≤200 with `preferences.md` to an OpenAI-compatible chat completions endpoint and returns `{"best": [...], "other": [...]}`. On any LLM or configuration error, `filter_jobs()` falls back to putting all regex-surviving jobs in `"other"` and appends `"llm filter broke: <error>"` to the email notes.

**Tech Stack:** Python 3.12+, uv, httpx, pytest, stdlib (`re`, `json`, `os`, `sys`, `pathlib`), Groq / OpenAI-compatible chat completions API.

**Spec:** `docs/superpowers/specs/2026-11-19-job-filtering-design.md`

## Global Constraints

- Dependencies: runtime `httpx` only; `pytest` in the `dev` dependency group. Run everything through uv: `uv run pytest`, `uv run python -m job_radar`.
- Job dict shape: `{"id": str, "title": str, "company": str, "location": str, "url": str}`.
- Tiered jobs dict shape: `{"best": list[dict], "other": list[dict]}`.
- LLM environment variables: `LLM_API_KEY` (fallback `GROQ_API_KEY`), `LLM_BASE_URL` (default `"https://api.groq.com/openai/v1"`), `LLM_MODEL` (default `"llama-3.3-70b-versatile"`).
- Never put API keys or credentials in code, tests, commits, or logs.

## Review Focus

1. **Substring false positives in regex drop-list**: Short tokens like `hr`, `sr`, `tax`, or `vp` must not match inside tech words or suffixes like `"Thread"`, `"SRL"`, `"Syntax"`, or `"MVP"`. Word boundaries (`\b`) and explicit phrases are pinned in Task 1.
2. **Duplicate, overlapping, or out-of-range LLM indices**: The LLM may return an index in both `"best"` and `"other"`, repeat an index (`[0, 0]`), or emit out-of-range/non-int values (`99`, `-1`, `"0"`). `"best"` wins over `"other"`, duplicates are ignored preserving order, and non-int or out-of-bounds indices are dropped. Pinned in Task 1.
3. **Chunk-local index mapping above 200 jobs**: When >200 jobs survive regex and are split into chunks of 200, indices `0..N-1` in chunk 2 must resolve against chunk 2's slice rather than chunk 1. Pinned in Task 1.
4. **Multiline LLM error notes in email subjects**: If 0 jobs survive or all sources fail and only a multiline `httpx` error note (`"llm filter broke: ...\nFor more information..."`) is present, `format_email` must collapse newlines in the subject header. Pinned in Task 2.
5. **Hermetic tests regardless of environment variables**: `uv run pytest` must pass deterministically whether `GROQ_API_KEY` / `LLM_API_KEY` are set or unset in the shell, without making real network calls. Pinned in Tasks 1 and 3.

---

### Task 1: Candidate `preferences.md` and `src/job_radar/filter.py`

**Files:**
- Create: `preferences.md`, `src/job_radar/filter.py`, `tests/test_filter.py`

**Interfaces:**
- Consumes: `HTTP` from `job_radar.client`, job dicts from `collect_results`.
- Produces:
  - `DEFAULT_PREFERENCES_PATH: Path` (`Path(__file__).resolve().parents[2] / "preferences.md"`)
  - `regex_prefilter(jobs: list[dict]) -> list[dict]`
  - `llm_filter(jobs: list[dict], preferences: str) -> dict[str, list[dict]]`
  - `filter_jobs(jobs_by_source: dict[str, list[dict]], preferences_path: Path = DEFAULT_PREFERENCES_PATH) -> tuple[dict[str, list[dict]], list[str]]`

- [ ] **Step 1: Create `preferences.md` at the repo root**

Write `preferences.md` with the candidate profile summary and `best` / `other` / `drop` classification rules from `docs/superpowers/specs/2026-11-19-job-filtering-design.md` (Section "Candidate `preferences.md` Content").

- [ ] **Step 2: Write failing tests in `tests/test_filter.py`**

```python
import httpx
import pytest

from helpers import job
from job_radar.filter import DEFAULT_PREFERENCES_PATH, filter_jobs, llm_filter, regex_prefilter


def titled_job(id: str, title: str, company: str = "Nokia") -> dict:
    return {**job(id, company), "title": title}


@pytest.mark.parametrize("title", [
    "Software Engineer Intern",
    "Working Student Python & AI (m/f/d)",
    "Werkstudent Softwareentwicklung (m/w/d)",
    "Junior Backend Developer (Python/FastAPI)",
    "Full Stack Engineer (TypeScript / React)",
    "AI / Machine Learning Engineer",
    "Data Engineer (Python, SQL)",
    "Rust Systems Programmer",
    "Embedded C++ Developer",
    "Platform & Threading Engineer",
    "Syntax & Compiler Engineer",
    "Software Developer (SRL)",
    "MVP Backend Engineer",
])
def test_regex_prefilter_keeps_target_roles(title):
    j = titled_job("1", title)
    assert regex_prefilter([j]) == [j]


@pytest.mark.parametrize("title", [
    "Senior Software Engineer",
    "Sr. Backend Developer",
    "Lead Data Engineer",
    "Team Lead Software Development",
    "Tech Lead Java",
    "Principal Systems Architect",
    "Staff Software Engineer",
    "Solution Architect",
    "Engineering Manager",
    "Director of Engineering",
    "Head of IT",
    "VP of Engineering",
    "HR Specialist",
    "Talent Acquisition Partner",
    "Junior Accountant",
    "Financial Controller",
    "Procurement Specialist",
    "Sachbearbeiter Einkauf (m/w/d)",
    "Legal Counsel",
    "Sales Representative",
    "Marketing Specialist",
    "Supply Chain Planner",
    "Mechanical Design Engineer",
    "Manufacturing Engineer",
    "IT Support Specialist with German",
    "Helpdesk Analyst (German Speaker)",
])
def test_regex_prefilter_drops_excluded_roles(title):
    assert regex_prefilter([titled_job("1", title)]) == []


def test_llm_filter_empty_jobs_skips_http(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert llm_filter([], "prefs") == {"best": [], "other": []}


def test_llm_filter_classifies_and_deduplicates_indices(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"best": [0, 0, 99, "bad"], "other": [0, 2, -1]}'}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("job_radar.filter.HTTP.post", fake_post)
    j0 = titled_job("1", "Software Engineer Intern", "Nokia")
    j1 = titled_job("2", "SAP FI Consultant", "SAP")
    j2 = titled_job("3", "Embedded C Developer", "Bosch")

    res = llm_filter([j0, j1, j2], "my preferences")
    assert res == {"best": [j0], "other": [j2]}
    assert len(calls) == 1
    url, headers, payload, _ = calls[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert payload["model"] == "llama-3.3-70b-versatile"
    assert payload["response_format"] == {"type": "json_object"}
    assert "0: [Nokia] Software Engineer Intern (Timișoara)" in payload["messages"][1]["content"]
    assert "u1" not in payload["messages"][1]["content"]


def test_llm_filter_chunks_over_200_jobs(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "custom-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1/")
    monkeypatch.setenv("LLM_MODEL", "custom-model")
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append(json)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"best": [0], "other": [1]}'}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("job_radar.filter.HTTP.post", fake_post)
    jobs = [titled_job(str(i), f"Developer {i}") for i in range(205)]
    res = llm_filter(jobs, "prefs")
    assert len(calls) == 2
    assert [j["id"] for j in res["best"]] == ["0", "200"]
    assert [j["id"] for j in res["other"]] == ["1", "201"]


def test_filter_jobs_zero_survivors_skips_llm_and_preferences(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    j_drop = titled_job("1", "Senior HR Manager", "Nokia")

    tiered, notes = filter_jobs({"Nokia": [j_drop]}, preferences_path=tmp_path / "missing.md")
    assert tiered == {"best": [], "other": []}
    assert notes == []
    assert "filter: 1 total -> 0 after regex -> 0 best, 0 other" in capsys.readouterr().out


def test_filter_jobs_fallback_when_api_key_missing(monkeypatch, capsys):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    j_keep = titled_job("1", "Python Intern", "Nokia")
    j_drop = titled_job("2", "Senior HR Manager", "Nokia")

    tiered, notes = filter_jobs({"Nokia": [j_keep, j_drop]})
    assert tiered == {"best": [], "other": [j_keep]}
    assert len(notes) == 1
    assert notes[0].startswith("llm filter broke:")
    assert "filter: 2 total -> 1 after regex -> 0 best, 1 other" in capsys.readouterr().out


def test_filter_jobs_fallback_on_malformed_llm_json(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def fake_post(url, *, headers, json, timeout):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not json"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("job_radar.filter.HTTP.post", fake_post)
    j_keep = titled_job("1", "Python Intern", "Nokia")
    tiered, notes = filter_jobs({"Nokia": [j_keep]})
    assert tiered == {"best": [], "other": [j_keep]}
    assert len(notes) == 1
    assert notes[0].startswith("llm filter broke:")


def test_default_preferences_file_exists():
    assert DEFAULT_PREFERENCES_PATH.is_file()
    text = DEFAULT_PREFERENCES_PATH.read_text(encoding="utf-8")
    assert "best" in text and "other" in text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_filter.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_radar.filter'`

- [ ] **Step 4: Implement `src/job_radar/filter.py`**

Implement `DEFAULT_PREFERENCES_PATH`, `_DROP_RE`, `regex_prefilter`, `llm_filter`, and `filter_jobs` per the spec (`docs/superpowers/specs/2026-11-19-job-filtering-design.md`, Section "Module Responsibilities -> 2. `src/job_radar/filter.py`"). Use `HTTP.post(..., timeout=30)` and `.raise_for_status()`. Raise `RuntimeError("GROQ_API_KEY or LLM_API_KEY not set")` in `llm_filter` when neither env var is set and `jobs` is non-empty.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_filter.py -q`
Expected: PASS (`46 passed`)

- [ ] **Step 6: Commit**

```bash
git add preferences.md src/job_radar/filter.py tests/test_filter.py
git commit -m "feat: add hybrid regex prefilter and LLM preference tiering"
```

---

### Task 2: Two-tier email formatting in `src/job_radar/mailer.py`

**Files:**
- Modify: `src/job_radar/mailer.py`, `tests/test_mailer.py`

**Interfaces:**
- Consumes: `tiered_jobs: dict[str, list[dict]]` (`{"best": [...], "other": [...]}`), `notes: list[str]`
- Produces: `format_email(tiered_jobs: dict[str, list[dict]], notes: list[str]) -> tuple[str, str] | None`

- [ ] **Step 1: Update and expand tests in `tests/test_mailer.py`**

```python
from email.message import EmailMessage

from helpers import job
from job_radar.mailer import format_email


def test_email_nothing_to_say():
    assert format_email({}, []) is None
    assert format_email({"best": [], "other": []}, []) is None


def test_email_renders_both_tiers_grouped_by_company():
    tiered = {
        "best": [job("1", "OPSWAT"), job("2", "Nokia")],
        "other": [job("3", "Porsche Engineering"), job("4", "Bosch")],
    }
    subject, body = format_email(tiered, [])
    assert subject == "2 best, 2 other jobs: Bosch, Nokia, OPSWAT, Porsche Engineering"
    assert "=== BEST MATCHES (2) ===" in body
    assert "=== OTHER TECH ROLES (2) ===" in body
    assert body.index("=== BEST MATCHES (2) ===") < body.index("Nokia") < body.index("OPSWAT")
    assert body.index("OPSWAT") < body.index("=== OTHER TECH ROLES (2) ===") < body.index("Bosch") < body.index("Porsche Engineering")


def test_email_best_only_singular_and_plural():
    subject, body = format_email({"best": [job("1", "Nokia")], "other": []}, [])
    assert subject == "1 best job: Nokia"
    assert "=== BEST MATCHES (1) ===" in body
    assert "=== OTHER TECH ROLES" not in body

    subject2, _ = format_email({"best": [job("1", "Nokia"), job("2", "OPSWAT")], "other": []}, [])
    assert subject2 == "2 best jobs: Nokia, OPSWAT"


def test_email_other_only_singular_and_plural():
    subject, body = format_email({"best": [], "other": [job("3", "OPSWAT")]}, [])
    assert subject == "1 job: OPSWAT"
    assert "=== OTHER TECH ROLES (1) ===" in body
    assert "=== BEST MATCHES" not in body

    subject2, _ = format_email({"best": [], "other": [job("1", "Nokia"), job("2", "OPSWAT")]}, [])
    assert subject2 == "2 jobs: Nokia, OPSWAT"


def test_email_notes_only():
    subject, body = format_email({"best": [], "other": []}, ["Haufe check broke: boom"])
    assert subject == "job alert: Haufe check broke: boom"
    assert "Haufe check broke: boom" in body


def test_email_notes_after_jobs():
    _, body = format_email({"best": [job("3", "OPSWAT")], "other": []}, ["Haufe check broke: boom"])
    assert body.index("T3") < body.index("Haufe check broke: boom")


def test_email_subject_is_single_line_for_multiline_errors():
    note = "llm filter broke: Client error '429 Too Many Requests' for url 'x'\nFor more information check: y"
    subject, body = format_email({}, [note])
    assert "\n" not in subject
    EmailMessage()["Subject"] = subject
    assert "For more information check: y" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mailer.py -q`
Expected: FAIL on tiered subject and section headers (`=== BEST MATCHES (2) ===`)

- [ ] **Step 3: Update `format_email` in `src/job_radar/mailer.py`**

Implement the two-tier subject and section rendering per the spec (`docs/superpowers/specs/2026-11-19-job-filtering-design.md`, Section "Module Responsibilities -> 3. `src/job_radar/mailer.py`"). Extract a small `_format_tier_block(header: str, jobs: list[dict]) -> str` helper that renders the tier header and company-grouped job blocks sorted by `company`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mailer.py -q`
Expected: PASS (`7 passed`)

- [ ] **Step 5: Commit**

```bash
git add src/job_radar/mailer.py tests/test_mailer.py
git commit -m "feat: format daily digest email into best and other tiers"
```

---

### Task 3: Wire `filter_jobs` into `runner.py`, workflow, and docs

**Files:**
- Modify: `src/job_radar/runner.py`, `tests/test_run.py`, `.github/workflows/check.yml`, `README.md`

**Interfaces:**
- Consumes: `collect_results`, `filter_jobs`, `format_email`, `send_email`
- Produces: `run(fetchers: dict, send: Callable[[str, str], None]) -> int`

- [ ] **Step 1: Update `tests/test_run.py` to test filtered and fallback runs offline**

```python
from helpers import job
from job_radar.runner import run


def boom():
    raise RuntimeError("down")


def test_run_filters_and_tiers_jobs(monkeypatch):
    monkeypatch.setattr(
        "job_radar.runner.filter_jobs",
        lambda jobs: ({"best": [job("1", "OPSWAT")], "other": [job("2", "Nokia")]}, []),
    )
    sent = []
    fetchers = {"OPSWAT": lambda: [job("1", "OPSWAT")], "Nokia": lambda: [job("2", "Nokia")]}
    assert run(fetchers, lambda s, b: sent.append((s, b))) == 0
    assert len(sent) == 1
    subject, body = sent[0]
    assert subject == "1 best, 1 other jobs: Nokia, OPSWAT"
    assert "=== BEST MATCHES (1) ===" in body
    assert "=== OTHER TECH ROLES (1) ===" in body


def test_run_falls_back_when_llm_key_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    sent = []
    assert run({"OPSWAT": lambda: [job("1", "OPSWAT"), {**job("2", "OPSWAT"), "title": "Senior HR Manager"}]},
               lambda s, b: sent.append((s, b))) == 0
    assert len(sent) == 1
    subject, body = sent[0]
    assert subject == "1 job: OPSWAT"
    assert "T1" in body and "Senior HR Manager" not in body
    assert "llm filter broke:" in body


def test_run_one_source_raising_does_not_stop_others(monkeypatch):
    monkeypatch.setattr("job_radar.runner.filter_jobs", lambda jobs: ({"best": [job("2", "OPSWAT")], "other": []}, []))
    sent = []
    assert run({"Haufe": boom, "OPSWAT": lambda: [job("2", "OPSWAT")]}, lambda s, b: sent.append((s, b))) == 0
    assert len(sent) == 1
    subject, body = sent[0]
    assert subject == "1 best job: OPSWAT"
    assert "T2" in body
    assert "Haufe check broke: down" in body


def test_run_smtp_failure_exits_nonzero(monkeypatch):
    monkeypatch.setattr("job_radar.runner.filter_jobs", lambda jobs: ({"best": [job("2")], "other": []}, []))
    def bad_send(s, b):
        raise OSError("smtp down")
    assert run({"OPSWAT": lambda: [job("2")]}, bad_send) != 0


def test_run_nothing_to_send(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    sent = []
    assert run({"OPSWAT": lambda: []}, lambda s, b: sent.append(s)) == 0
    assert sent == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_run.py -q`
Expected: FAIL (`AttributeError: <module 'job_radar.runner'> has no attribute 'filter_jobs'`)

- [ ] **Step 3: Wire `filter_jobs` in `src/job_radar/runner.py` and update `.github/workflows/check.yml` and `README.md`**

In `src/job_radar/runner.py`:
- Import `filter_jobs` from `job_radar.filter`.
- After printing per-source counts, call `tiered_jobs, filter_notes = filter_jobs(jobs)` and `notes.extend(filter_notes)`.
- Pass `tiered_jobs, notes` to `format_email(tiered_jobs, notes)`.

In `.github/workflows/check.yml`:
- Add `GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}` under `env:` for the `uv run --locked python -m job_radar` step.

In `README.md`:
- Mention `GROQ_API_KEY` (and optional `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`), `preferences.md`, and `src/job_radar/filter.py` in the Secrets and Layout bullets.

- [ ] **Step 4: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS (all tests across `test_filter.py`, `test_mailer.py`, `test_run.py`, `test_state.py`, `test_smartrecruiters.py`, `test_successfactors.py` green)

- [ ] **Step 5: Commit**

```bash
git add src/job_radar/runner.py tests/test_run.py .github/workflows/check.yml README.md
git commit -m "feat: wire hybrid job filtering into runner and workflow"
```
