# Job Filtering & Preference Tiering — Design Spec

Date: 2026-11-19

## Intent

Since commit `3e0a93e`, `job_radar` runs statelessly once per day and emails all active Timișoara/Romania job postings across 24 employers (~300–400 jobs/day). Because every active opening is included on every run, early-career software/AI/data roles are buried under hundreds of senior, management, and non-technical postings.

This change adds a stateless two-stage filter and tiering pipeline between `collect_results()` and `format_email()`:
1. **Regex pre-filter (`regex_prefilter`)**: deterministically drops obvious senior/management roles, non-technical departments, and German-fluency-required titles at zero token cost.
2. **LLM preference classifier (`llm_filter`)**: reads `preferences.md` (distilled from Paul's CV) and classifies surviving job titles via an OpenAI-compatible chat completions API (defaulting to Groq `llama-3.3-70b-versatile`) into two priority tiers (`best` and `other`), dropping remaining non-matches.

Success: Paul receives a single daily digest email with relevant roles organized into `=== BEST MATCHES ===` and `=== OTHER TECH ROLES ===` sections (each grouped alphabetically by company), while preserving graceful fallback if the LLM provider fails or is unconfigured.

## Architecture & Data Flow

```text
fetchers (24 sources)
  → collect_results()          # deduplicate by job["id"] per source (state.py)
  → filter_jobs()              # regex_prefilter() + llm_filter() (filter.py)
  → format_email()             # render tiered sections grouped by company (mailer.py)
  → send_email() / --dry-run
```

### Module Responsibilities

1. **`preferences.md` (repo root)**
   - Human-editable plain Markdown file containing Paul's candidate profile summary and classification rules for `best`, `other`, and `drop`.
   - Loaded by `src/job_radar/filter.py` from the repository root (with an overridable path argument for testing).

2. **`src/job_radar/filter.py` (new module)**
   - `regex_prefilter(jobs: list[dict]) -> list[dict]`:
     - Tests each job's `title` against a compiled case-insensitive regex (`_DROP_RE`) matching:
       - Seniority exclusions: `\b(senior|sr\.?|lead|team\s*lead|tech\s*lead|principal|staff|architect|manager|director|head\s+of|vp|vice\s+president|chief|expert)\b`
       - Non-tech department exclusions: `\b(hr|human\s+resources|recruiter|recruiting|talent\s+acquisition|payroll|finance|financial|accountant|accounting|controlling|controller|tax|audit|treasury|procurement|purchasing|buyer|einkauf|legal|counsel|paralegal|sales|account\s+executive|marketing|copywriter|logistics|supply\s+chain|warehouse|customs|mechanical|electrical\s+design|wiring|harness|manufacturing|production\s+planner|plant|facility|receptionist|assistant\s+to)\b`
       - Language exclusions: `\b(german\s+speaker|with\s+german|german\s+language)\b`
     - Returns only jobs whose `title` does not match `_DROP_RE`.
   - `llm_filter(jobs: list[dict], preferences: str) -> dict[str, list[dict]]`:
     - Provider-agnostic OpenAI-compatible HTTP client using `httpx`:
       - API key: `os.environ.get("LLM_API_KEY") or os.environ.get("GROQ_API_KEY")`
       - Endpoint: `os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/") + "/chat/completions"`
       - Model: `os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")`
     - If `jobs` is empty, returns `{"best": [], "other": []}` without making an HTTP call.
     - Batches `jobs` in chunks of up to `200` items per request to stay well within Groq's 12,000 TPM free-tier limit.
     - Formats each chunk as numbered lines without URLs:
       `0: [Company] Title (Location)`
     - Sends system message with `preferences` + strict JSON output instructions (`{"best": [<int>, ...], "other": [<int>, ...]}`), `temperature=0`, and `response_format={"type": "json_object"}`.
     - Maps valid integer indices back to job dicts in `"best"` and `"other"`. If an index appears in both, `"best"` wins; out-of-range or non-integer indices are ignored; omitted indices are dropped.
   - `filter_jobs(jobs_by_source: dict[str, list[dict]], preferences_path: Path = ...) -> tuple[dict[str, list[dict]], list[str]]`:
     - Flattens `jobs_by_source` into a list of jobs (`raw_count`).
     - Applies `regex_prefilter(all_jobs)` to get `surviving_jobs` (`regex_count`).
     - If `surviving_jobs` is non-empty, loads `preferences_path` and calls `llm_filter(surviving_jobs, preferences_text)` (otherwise returns `{"best": [], "other": []}` without reading preferences or calling the API).
     - On any exception in reading preferences or calling `llm_filter` (missing API key, HTTP error, rate limit, malformed JSON), catches the exception, logs it to `sys.stderr`, appends `"llm filter broke: <error>"` to `notes`, and falls back to `{"best": [], "other": surviving_jobs}` so the regex-filtered digest is still emailed.
     - Prints summary line to stdout: `filter: {raw_count} total -> {regex_count} after regex -> {len(best)} best, {len(other)} other`.

3. **`src/job_radar/mailer.py` (modified)**
   - `format_email(tiered_jobs: dict[str, list[dict]], notes: list[str]) -> tuple[str, str] | None`:
     - Accepts `tiered_jobs` keyed by `"best"` and `"other"` (missing keys default to `[]`).
     - Returns `None` if both `"best"` and `"other"` are empty and `notes` is empty.
     - Subject line rules (with singular/plural `"job"` / `"jobs"`):
       - Both `best` and `other` non-empty: `"{len(best)} best, {len(other)} other jobs: {companies}"`
       - Only `best` non-empty: `"{len(best)} best job{'s' if len(best) != 1 else ''}: {companies}"`
       - Only `other` non-empty: `"{len(other)} job{'s' if len(other) != 1 else ''}: {companies}"`
       - Zero jobs, only notes: `"job alert: " + "; ".join(notes)`
       - `{companies}` is the sorted unique list of company names across all included jobs (`best` + `other`).
     - Body layout:
       - Whenever `best` has jobs: renders `=== BEST MATCHES ({len(best)}) ===` followed by company-grouped blocks (sorted alphabetically by company).
       - Whenever `other` has jobs: renders `=== OTHER TECH ROLES ({len(other)}) ===` followed by company-grouped blocks (sorted alphabetically by company).
       - Appends `notes` at the bottom separated by a blank line.

4. **`src/job_radar/runner.py` (modified)**
   - Calls `collect_results(results)` to obtain `jobs_by_source, notes`.
   - Calls `filter_jobs(jobs_by_source)` to obtain `tiered_jobs, filter_notes` and extends `notes` with `filter_notes`.
   - Passes `tiered_jobs, notes` to `format_email(tiered_jobs, notes)`.

5. **`.github/workflows/check.yml` & `README.md` (modified)**
   - Pass `GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}` in the workflow environment.
   - Document `GROQ_API_KEY` (and optional `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`) and `preferences.md` in `README.md`.

## Candidate `preferences.md` Content

The initial `preferences.md` at the repo root is generated from `docs/Paul_Hondola_CV.tex`:
- Final-year B.Sc. Computer Engineering student at Universitatea Politehnica Timișoara (graduating Jul 2027, GPA 9.72/10).
- Experience: Software Engineer Intern at Nokia (Python, pandas, MariaDB, ETL pipelines, Jenkins, GitLab, Power BI), Full Stack Developer Intern at Hibyte (TypeScript, Angular, NestJS, Payload CMS, Supabase), Reverse Engineering & Malware Analysis Trainee at Bitdefender × LigaAC (C, Python, x86 Assembly, IDA Pro, Frida).
- Projects: Groundly (Python, FastMCP, SQLite, bge-m3, hybrid RAG/reranking), EchoCare (Python, FastAPI, PostgreSQL, Kotlin, SvelteKit), gemm-bench (Rust, SIMD/NEON, Rayon, Metal), Vibecodium (TypeScript, React, Bun, Docker), MPI/OpenMP Image Processing (C).
- Tier definitions:
  - **`best`**: Intern, Working Student (Werkstudent), Trainee, Graduate, Junior, Entry-Level, or unlabelled-seniority early-career roles (0–2 years) in backend/full-stack/general software engineering, AI/ML/NLP/LLM/RAG/data engineering/Python data pipelines, or systems/HPC/cybersecurity/reverse engineering/DevOps.
  - **`other`**: Early-career or mid-level tech roles in adjacent areas (embedded C/C++, automotive software, QA/test automation, BI/data analytics, mobile Kotlin/Android, IT support/sysadmin) or mid-level software/data/AI engineering roles matching the stack.
  - **`drop`**: Senior/Staff/Principal/Lead/Architect/Manager/Director/Head/VP roles, non-engineering departments (HR, Finance, Accounting, Procurement, Legal, Sales, Marketing, Logistics, Mechanical/Electrical/Manufacturing plant roles), titles requiring German fluency, and pure ERP functional consulting (e.g. SAP FI/CO, Workday functional).

## Error Handling & Edge Cases

- **Missing `GROQ_API_KEY` / `LLM_API_KEY`**: Treated as an `llm_filter` failure (`RuntimeError("GROQ_API_KEY or LLM_API_KEY not set")`). Caught by `filter_jobs()`, which falls back to placing all regex-surviving jobs into `"other"` and adds `"llm filter broke: GROQ_API_KEY or LLM_API_KEY not set"` to the email notes.
- **LLM HTTP timeout / 429 / 5xx / invalid JSON**: Caught by `filter_jobs()`, falls back to regex-surviving jobs in `"other"` with `"llm filter broke: ..."` note.
- **0 jobs survive regex**: `llm_filter` is not called (0 tokens used); if there are no error notes, no email is sent.
- **All jobs dropped by LLM**: `tiered_jobs` has `{"best": [], "other": []}`; if there are no error notes, no email is sent.

## Testing Strategy

All unit tests run offline via `uv run pytest`:
- `tests/test_filter.py`:
  - `regex_prefilter` keeps target titles (Intern, Working Student, Werkstudent, Junior, Software Engineer, Python, AI/ML, Data, Rust, C++, Full Stack, Embedded) and drops Senior/Lead/Manager/Architect, non-tech departments (HR, Finance, Purchasing, Einkauf, Sales, Legal, Mechanical, Manufacturing), and German-speaker roles.
  - `llm_filter` formats numbered lines, parses `{"best": [...], "other": [...]}`, deduplicates/ignores invalid indices, batches >200 jobs, and skips HTTP when input is empty.
  - `filter_jobs` falls back gracefully to regex-filtered jobs in `"other"` and appends `"llm filter broke: ..."` when the LLM call raises or API key is missing.
- `tests/test_mailer.py`:
  - Formats two-tier emails (`=== BEST MATCHES (N) ===` and `=== OTHER TECH ROLES (M) ===`), grouped by company within each tier, with updated subject counts and error notes at the bottom.
- `tests/test_run.py`:
  - Verifies end-to-end `run()` integration with `filter_jobs` and fallback notes.
