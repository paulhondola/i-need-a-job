# Flag-Based Romanian City Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--city` CLI flag (comma-separated or repeated Romanian cities, `--city all`, defaulting to Timișoara) backed by a stateless `CityFilter` passed explicitly to all 11 job sources, reflected in email subjects, and configurable in GitHub Actions.

**Architecture:** A new `src/job_radar/cities.py` module defines `CitySpec`, `ROMANIAN_CITIES`, `CityFilter`, `DEFAULT_CITY_FILTER`, and `parse_city_filter()`. All 11 source fetchers accept `city_filter: CityFilter = DEFAULT_CITY_FILTER` (`beesite` and `telekom` switch to Romania-wide fetch + client-side filtering; `rinf` discovers sidebar city filters or uses `country=Romania` for `all`; `successfactors` queries `city_filter.search_terms()` and deduplicates by job ID). `runner.py` parses `--city`, passes `city_filter` through `ThreadPoolExecutor` to each fetcher, and forwards `city_filter.label` to `mailer.format_email()`.

**Tech Stack:** Python 3.12+, uv, httpx, pytest, ruff, pyrefly, stdlib (`argparse`, `dataclasses`, `functools`, `html`, `re`, `typing`, `unicodedata`).

**Spec:** `docs/superpowers/specs/2026-11-19-city-filtering-design.md`

## Global Constraints

- Runtime dependencies remain `httpx` and `python-dotenv` only; no new packages. Run commands via `uv run` (`uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyrefly check`).
- Job dict shape stays `{"id": str, "title": str, "company": str, "location": str, "url": str}`.
- Default run with no `--city` flag targets Timișoara (`DEFAULT_CITY_FILTER`, `label == "Timișoara"`).
- Bare `"Romania"` locations and explicit Romania-remote postings remain matched by default when specific cities are selected.
- `preferences.md`, `src/job_radar/filter.py`, and the 25 tracked companies in `src/job_radar/sources/__init__.py` stay unchanged in scope.
- Every commit must pass `lefthook.yml` (`ruff check`, `ruff format`, `pyrefly check`, `pytest -q`).

## Review Focus

1. **Word-boundary and country-code precision**: Short city aliases (`arad`, `iasi`) must not match substrings inside unrelated words (`"Colorado"`, `"Enthusiastic"`), hyphen/space/diacritic variants (`"Cluj Napoca"`, `"Târgu-Mureș"`, `"Timişoara"`, `"București"`) must match, and lowercase `"ro"` inside prose or non-uppercase tokens must not trigger the `RO` country-code check. Pinned in Task 1.
2. **Duplicate, aliased, mixed, and blank `--city` inputs**: Inputs like `"bucharest, București"`, `"baia-mare, baia mare"`, repeated `--city` flags, and `"timisoara,all"` must deduplicate or subsume cleanly, while blank inputs (`""`, `" , "`) must fail fast with CLI exit code 2 before any HTTP calls. Pinned in Tasks 1 and 4.
3. **Cross-query deduplication on multi-query server-side sources**: Overlapping SuccessFactors keyword results (`Bucharest` + `Bucuresti` + `Romania`) must deduplicate by job ID preserving first-seen order; overlapping `rinf.tech` city results (`Timisoara` + `Cluj-Napoca`) must deduplicate by job ID while combining distinct city names (`"Timisoara; Cluj-Napoca"`). Pinned in Task 3.
4. **Live API markup/whitespace quirks on rewritten sources**: Porsche Beesite emits trailing spaces in `CityName` (`"Bucharest "`) and could omit `PositionLocation`; `rinf.tech` could redesign its sidebar HTML so zero `name="city-..."` checkboxes parse. Beesite must strip/guard safely; `rinf.py` must raise `ValueError` when zero checkboxes are found, while returning `[]` when checkboxes exist but none match. Pinned in Task 3.
5. **Unlisted Romanian towns under `--city all` on country-scoped APIs**: On `smartrecruiters`, `beesite`, `telekom`, and `rinf`, `--city all` must retain Romania jobs in towns outside the 15-city catalog (e.g. `"Ghiroda"`, `"Jucu"`). Pinned in Tasks 2 and 3.

---

## File Structure

- **Create:** `src/job_radar/cities.py` — `fold()`, `CitySpec`, `ROMANIAN_CITIES`, `CityFilter`, `DEFAULT_CITY_FILTER`, `parse_city_filter()`.
- **Create:** `tests/test_cities.py`, `tests/test_beesite.py`, `tests/test_telekom.py`.
- **Modify:** `src/job_radar/sources/{greenhouse,lever,oracle,personio,teamtailor,smartrecruiters,workday}.py` + `tests/test_{greenhouse,oracle,smartrecruiters,workday}.py` (Task 2).
- **Modify:** `src/job_radar/sources/{beesite,telekom,rinf,successfactors}.py`, `src/job_radar/state.py`, `tests/test_{rinf,successfactors,state}.py` (Task 3).
- **Modify:** `src/job_radar/sources/__init__.py`, `src/job_radar/mailer.py`, `src/job_radar/runner.py`, `src/job_radar/__init__.py`, `.github/workflows/check.yml`, `README.md`, `tests/test_{mailer,run}.py` (Task 4).

---

### Task 1: City catalog, parser, and matcher (`src/job_radar/cities.py`)

**Files:**
- Create: `src/job_radar/cities.py`, `tests/test_cities.py`

**Interfaces:**
- Consumes: stdlib only (`dataclasses`, `re`, `unicodedata`).
- Produces (exported from `job_radar.cities`):
  - `fold(text: str) -> str`
  - `CitySpec(canonical: str, aliases: tuple[str, ...], search_terms: tuple[str, ...])` (frozen dataclass)
  - `ROMANIAN_CITIES: tuple[CitySpec, ...]` (15 hubs per spec table)
  - `CityFilter(cities: tuple[CitySpec, ...], is_all: bool = False)` (frozen dataclass) with:
    - `.label: str` property
    - `.matches(location: str) -> bool`
    - `.search_terms() -> tuple[str, ...]`
  - `DEFAULT_CITY_FILTER: CityFilter` (Timișoara)
  - `parse_city_filter(raw: list[str] | None) -> CityFilter`

- [ ] **Step 1: Write failing tests in `tests/test_cities.py`**

```python
import pytest

from job_radar.cities import (
    DEFAULT_CITY_FILTER,
    ROMANIAN_CITIES,
    CityFilter,
    fold,
    parse_city_filter,
)


def test_fold_strips_all_romanian_diacritics_and_normalizes_whitespace():
    assert fold("  Timișoara  ") == "timisoara"
    assert fold("Timişoara") == "timisoara"
    assert fold("Târgu   Mureș") == "targu mures"
    assert fold("București,  Iași,  Brașov,  Constanța,  Ploiești,  Bacău") == (
        "bucuresti, iasi, brasov, constanta, ploiesti, bacau"
    )
    assert fold("Întorsura ĂÂÎȘŞȚŢ") == "intorsura aaisstt"


def test_parse_city_filter_defaults_to_timisoara():
    cf = parse_city_filter(None)
    assert isinstance(cf, CityFilter)
    assert cf == DEFAULT_CITY_FILTER
    assert cf.label == "Timișoara"
    assert not cf.is_all


def test_parse_city_filter_comma_separated_repeated_and_deduplicated():
    cf = parse_city_filter(["timisoara, cluj", "Cluj-Napoca", "bucharest, București"])
    assert [c.canonical for c in cf.cities] == ["Timișoara", "Cluj-Napoca", "Bucharest"]
    assert cf.label == "Timișoara, Cluj-Napoca, Bucharest"


def test_parse_city_filter_normalizes_hyphens_and_spaces_for_catalog_and_fallback():
    cf_cat = parse_city_filter(["targu-mures", "Târgu Mureș", "tg. mures"])
    assert [c.canonical for c in cf_cat.cities] == ["Târgu Mureș"]

    cf_fb = parse_city_filter(["baia-mare, baia mare", "Petroșani"])
    assert [c.canonical for c in cf_fb.cities] == ["Baia-Mare", "Petroșani"]
    assert cf_fb.cities[0].aliases == ("baia-mare",)
    assert cf_fb.cities[0].search_terms == ("Baia-Mare",)
    assert cf_fb.cities[1].aliases == ("petrosani",)
    assert cf_fb.cities[1].search_terms == ("Petrosani",)


@pytest.mark.parametrize("raw", [["all"], ["Romania"], ["timisoara,all"], ["cluj", "ROMANIA"]])
def test_parse_city_filter_all_subsumes_individual_cities(raw):
    cf = parse_city_filter(raw)
    assert cf.is_all
    assert cf.cities == ()
    assert cf.label == "Romania"


@pytest.mark.parametrize("raw", [[""], ["   "], [", ,"], ["", "  ,  "]])
def test_parse_city_filter_rejects_blank_input(raw):
    with pytest.raises(ValueError, match="city"):
        parse_city_filter(raw)


@pytest.mark.parametrize(
    "loc",
    [
        "Timișoara",
        "Timişoara",
        "Timisoara",
        "TIMISOARA",
        "Timișoara, Timiș, Romania",
        "Romania, Timisoara",
        "Timisoara (Hybrid), RO",
        "Romania",
        " romania ",
        "Remote - Romania",
        "Romania (Remote)",
        "Remote, RO",
        "Bucharest, Romania (Remote)",
    ],
)
def test_default_filter_matches_timisoara_bare_romania_and_romania_remote(loc):
    assert DEFAULT_CITY_FILTER.matches(loc)


@pytest.mark.parametrize(
    "loc",
    [
        "Romania, Bucharest",
        "Bucharest, Romania (Hybrid)",
        "Cluj-Napoca, Romania",
        "Budapest, Hungary",
        "EMEA - Remote",
        "Remote - Europe",
        "Remote, ro",
        "",
        "   ",
    ],
)
def test_default_filter_rejects_other_cities_and_non_romania_remote(loc):
    assert not DEFAULT_CITY_FILTER.matches(loc)


def test_word_boundary_prevents_substring_collisions_and_matches_aliases():
    arad = parse_city_filter(["arad"])
    assert arad.matches("Arad, Romania")
    assert not arad.matches("Denver, Colorado")
    assert not arad.matches("Paradis, Germany")

    iasi = parse_city_filter(["iasi"])
    assert iasi.matches("Iași, Romania")
    assert not iasi.matches("Enthusiastic Team, Berlin")

    buc = parse_city_filter(["bucharest"])
    assert buc.matches("București, Sector 1, Romania")
    assert buc.matches("Bucuresti, RO")
    assert buc.matches("Bucharest, Romania")
    assert not buc.matches("Cluj-Napoca, Romania")

    cluj = parse_city_filter(["cluj"])
    assert cluj.matches("Cluj-Napoca, RO, 400002")
    assert cluj.matches("Cluj Napoca, Romania")
    assert cluj.matches("Cluj")

    tm_cj = parse_city_filter(["timisoara,cluj"])
    assert tm_cj.matches("Timisoara, RO")
    assert tm_cj.matches("Cluj-Napoca, Romania")
    assert not tm_cj.matches("Bucharest, Romania")

    fb = parse_city_filter(["baia-mare"])
    assert fb.matches("Baia Mare, Romania")
    assert fb.matches("Baia-Mare, RO")


@pytest.mark.parametrize(
    "loc",
    [
        "Romania",
        "Bucharest, Romania",
        "TIMISOARA, TM, RO, 307160",
        "Brasov, RO",
        "Remote (RO)",
        "Cluj",
        "București",
        "Târgu-Mureș",
    ],
)
def test_all_romania_matches_country_ro_code_and_catalog_cities(loc):
    cf = parse_city_filter(["all"])
    assert cf.matches(loc)


@pytest.mark.parametrize(
    "loc",
    [
        "Budapest, Hungary",
        "EMEA - Remote",
        "Pro Engineering, Berlin",
        "Remote, ro-land",
        "Denver, Colorado",
        "",
    ],
)
def test_all_romania_rejects_non_romania_locations(loc):
    cf = parse_city_filter(["all"])
    assert not cf.matches(loc)


def test_search_terms_for_specific_cities_and_all():
    assert DEFAULT_CITY_FILTER.search_terms() == ("Timisoara", "Romania")
    assert parse_city_filter(["bucharest,cluj"]).search_terms() == (
        "Bucharest",
        "Bucuresti",
        "Cluj",
        "Romania",
    )
    all_terms = parse_city_filter(["all"]).search_terms()
    assert all_terms[0] == "Romania"
    assert "Timisoara" in all_terms
    assert "Bucharest" in all_terms
    assert "Bucuresti" in all_terms
    assert "Cluj" in all_terms
    assert len(all_terms) == len(set(all_terms))
    assert len(ROMANIAN_CITIES) == 15
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cities.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_radar.cities'`

- [ ] **Step 3: Implement `src/job_radar/cities.py`**

Implement `fold`, `CitySpec`, `ROMANIAN_CITIES` (exact 15-entry table from `docs/superpowers/specs/2026-11-19-city-filtering-design.md`), `CityFilter`, `DEFAULT_CITY_FILTER`, and `parse_city_filter` per the spec.
- Build each alias regex by splitting the folded alias on `[-\s]+`, escaping each part with `re.escape`, joining with `[-\s]+`, and wrapping in `(?<!\w)...(?!\w)`. Precompile a combined regex per `CityFilter` (e.g. via `functools.cached_property` or `__post_init__` with `object.__setattr__` and `field(init=False, repr=False, compare=False)` so `CityFilter` stays frozen and hashable/comparable).
- Use `re.compile(r"(?:^|[\s,(/-])RO(?:$|[\s,)/-])")` on the **original-case** location string for `_has_ro_code`.
- Normalize lookup keys with `re.sub(r"[-\s]+", " ", fold(token))` for both catalog indexing and deduplication in `parse_city_filter()`.

- [ ] **Step 4: Run tests, lint, and typecheck**

Run: `uv run pytest tests/test_cities.py -q && uv run pyrefly check && uv run ruff check src/job_radar/cities.py tests/test_cities.py`
Expected: PASS (all `test_cities.py` tests pass, 0 pyrefly errors, 0 ruff errors)

- [ ] **Step 5: Commit**

```bash
git add src/job_radar/cities.py tests/test_cities.py
git commit -m "feat: add Romanian city catalog and CityFilter matcher"
```

---

### Task 2: Parameterize the 7 client-side and dynamic-facet sources

**Files:**
- Modify: `src/job_radar/sources/greenhouse.py`, `src/job_radar/sources/lever.py`, `src/job_radar/sources/oracle.py`, `src/job_radar/sources/personio.py`, `src/job_radar/sources/teamtailor.py`, `src/job_radar/sources/smartrecruiters.py`, `src/job_radar/sources/workday.py`
- Modify: `tests/test_greenhouse.py`, `tests/test_oracle.py`, `tests/test_smartrecruiters.py`, `tests/test_workday.py`

**Interfaces:**
- Consumes: `CityFilter`, `DEFAULT_CITY_FILTER`, `parse_city_filter` from `job_radar.cities`.
- Produces (each source's `fetch` gains trailing `city_filter: CityFilter = DEFAULT_CITY_FILTER`):
  - `greenhouse.fetch(board: str, company: str, city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`
  - `lever.fetch(slug: str, company: str, api_host: str = "api.lever.co", city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`
  - `oracle.fetch(api_host: str, site: str, job_url_prefix: str, company: str, city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`
  - `personio.fetch(slug: str, company: str, tld: str = "de", job_url: str = "", city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`
  - `teamtailor.fetch(slug: str, company: str, city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`
  - `smartrecruiters.fetch(slug: str, company: str, city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`
  - `workday.fetch(host: str, tenant: str, site: str, company: str, city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`

- [ ] **Step 1: Add failing multi-city and `all` tests to `tests/test_greenhouse.py`, `tests/test_oracle.py`, `tests/test_smartrecruiters.py`, and `tests/test_workday.py`**

Add one focused test to each of the four existing test files (keeping all existing default-Timișoara tests untouched):
- In `tests/test_greenhouse.py`: `test_greenhouse_filters_by_custom_city_filter(monkeypatch)` — reuses a payload containing Timișoara (`103`), Bucharest (`104`), and Athens-only (`105`), asserts `greenhouse.fetch(board="acme", company="Acme", city_filter=parse_city_filter(["bucharest"]))` returns only `["104"]`, and `parse_city_filter(["timisoara,bucharest"])` returns `["103", "104"]`.
- In `tests/test_oracle.py`: `test_oracle_filters_by_custom_city_filter(monkeypatch)` — asserts `oracle.fetch(..., city_filter=parse_city_filter(["cluj"]))` returns only `["13"]` (Cluj-Napoca) and `parse_city_filter(["all"])` returns `["11", "12", "13"]` (skipping null-location `"10"`).
- In `tests/test_smartrecruiters.py`: `test_smartrecruiters_custom_city_and_all_keeps_unlisted_romania_town(monkeypatch)` — page has `posting("1", "Timișoara")`, `posting("2", remote=True)`, `posting("3", "Bucharest")`, `posting("4", "Ghiroda")`; asserts `parse_city_filter(["bucharest"])` returns `["2", "3"]` and `parse_city_filter(["all"])` returns `["1", "2", "3", "4"]`.
- In `tests/test_workday.py`: `test_workday_multi_city_passes_all_matched_facet_ids(monkeypatch)` — facets include `loc-tm` (`"Romania, Timisoara"`), `loc-b` (`"Romania, Bucharest"`), and `loc-de` (`"Germany, Munich"`); asserts `workday.fetch(..., city_filter=parse_city_filter(["timisoara,bucharest"]))` sends `appliedFacets == {"locations": ["loc-tm", "loc-b"]}`.

- [ ] **Step 2: Run tests to verify the new tests fail**

Run: `uv run pytest tests/test_greenhouse.py tests/test_oracle.py tests/test_smartrecruiters.py tests/test_workday.py -q`
Expected: FAIL with `TypeError: fetch() got an unexpected keyword argument 'city_filter'`

- [ ] **Step 3: Update all 7 source modules**

In `greenhouse.py`, `lever.py`, `oracle.py`, `personio.py`, `teamtailor.py`, `smartrecruiters.py`, and `workday.py`:
- Replace `from job_radar.state import matches_timisoara` with `from job_radar.cities import DEFAULT_CITY_FILTER, CityFilter`.
- Add `city_filter: CityFilter = DEFAULT_CITY_FILTER` as the trailing parameter of `fetch(...)`.
- Replace `matches_timisoara(...)` calls with `city_filter.matches(...)`.
- In `smartrecruiters.py`, change the keep condition to `p["location"].get("remote") or city_filter.is_all or city_filter.matches(p["location"].get("city") or "")`.

- [ ] **Step 4: Run full test suite, lint, and typecheck**

Run: `uv run pytest -q && uv run pyrefly check && uv run ruff check src tests`
Expected: PASS (all existing + new tests pass, 0 pyrefly errors, 0 ruff errors)

- [ ] **Step 5: Commit**

```bash
git add src/job_radar/sources/greenhouse.py src/job_radar/sources/lever.py src/job_radar/sources/oracle.py src/job_radar/sources/personio.py src/job_radar/sources/teamtailor.py src/job_radar/sources/smartrecruiters.py src/job_radar/sources/workday.py tests/test_greenhouse.py tests/test_oracle.py tests/test_smartrecruiters.py tests/test_workday.py
git commit -m "feat: pass CityFilter to client-side and Workday sources"
```

---

### Task 3: Parameterize the 4 server-side sources (`beesite`, `telekom`, `rinf`, `successfactors`) and clean up `state.py`

**Files:**
- Create: `tests/test_beesite.py`, `tests/test_telekom.py`
- Modify: `src/job_radar/sources/beesite.py`, `src/job_radar/sources/telekom.py`, `src/job_radar/sources/rinf.py`, `src/job_radar/sources/successfactors.py`, `src/job_radar/state.py`
- Modify: `tests/test_rinf.py`, `tests/test_successfactors.py`, `tests/test_state.py`

**Interfaces:**
- Consumes: `CityFilter`, `DEFAULT_CITY_FILTER`, `parse_city_filter` from `job_radar.cities`.
- Produces:
  - `beesite.fetch_porsche(city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`
  - `telekom.fetch(city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`
  - `rinf.fetch(city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`
  - `successfactors.fetch(host: str, company: str, city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]`
  - `state.py`: exports only `collect_results(results: dict) -> tuple[list[dict], list[str]]` (`matches_timisoara` removed).

- [ ] **Step 1: Write failing tests in `tests/test_beesite.py`, `tests/test_telekom.py`, `tests/test_rinf.py`, and `tests/test_successfactors.py`**

1. `tests/test_beesite.py`:
```python
import json

import httpx

from job_radar.cities import parse_city_filter
from job_radar.sources import beesite


def _item(id: int, title: str, city: str | None) -> dict:
    locs = [{"CityName": city}] if city is not None else []
    return {
        "MatchedObjectDescriptor": {
            "ID": id,
            "PositionTitle": title,
            "PositionURI": f"https://jobs.porsche.com/{id}",
            "PositionLocation": locs,
            "ParentOrganizationName": "Porsche Engineering Romania",
        }
    }


def test_beesite_queries_romania_only_strips_city_and_filters(monkeypatch):
    seen_criteria = []
    payload = {
        "SearchResult": {
            "SearchResultItems": [
                _item(1, "Python Dev", "Timisoara"),
                _item(2, "Cloud Dev", "Bucharest "),
                _item(3, "Embedded Dev", "Cluj"),
                _item(4, "Plant IT", "Jucu"),
                _item(5, "Missing Loc", None),
            ]
        }
    }

    def handler(req: httpx.Request) -> httpx.Response:
        query = json.loads(req.url.params["data"])
        seen_criteria.append(query["SearchCriteria"])
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(beesite, "HTTP", client)

    tm = beesite.fetch_porsche()
    assert [j["id"] for j in tm] == ["1"]
    assert all(c["CriterionName"] != "PositionLocation.City" for c in seen_criteria[0])
    assert {"CriterionName": "PositionLocation.Country", "CriterionValue": ["176"]} in seen_criteria[0]

    buc_cluj = beesite.fetch_porsche(city_filter=parse_city_filter(["bucharest,cluj"]))
    assert [(j["id"], j["location"]) for j in buc_cluj] == [
        ("2", "Bucharest"),
        ("3", "Cluj"),
    ]

    all_ro = beesite.fetch_porsche(city_filter=parse_city_filter(["all"]))
    assert [j["id"] for j in all_ro] == ["1", "2", "3", "4", "5"]
```

2. `tests/test_telekom.py`:
```python
import httpx

from job_radar.cities import parse_city_filter
from job_radar.sources import telekom


def _posting(req_id: str, city: str) -> dict:
    return {"requisition_id": req_id, "title": f"Role {req_id}", "city": city}


def test_telekom_queries_romania_and_filters_by_city_and_all(monkeypatch):
    seen_locations = []
    pages = {
        "1": {
            "data": [_posting("1", "Timișoara"), _posting("2", "Bucharest")],
            "pagination_info": {"number_of_pages": 2},
        },
        "2": {
            "data": [_posting("3", "Romania"), _posting("4", "Jucu")],
            "pagination_info": {"number_of_pages": 2},
        },
    }

    def handler(req: httpx.Request) -> httpx.Response:
        seen_locations.append(req.url.params["location"])
        return httpx.Response(200, json=pages[req.url.params["page"]])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(telekom, "HTTP", client)

    tm = telekom.fetch()
    assert set(seen_locations) == {"Romania"}
    assert [j["id"] for j in tm] == ["1", "3"]

    buc = telekom.fetch(city_filter=parse_city_filter(["bucuresti"]))
    assert [j["id"] for j in buc] == ["2", "3"]

    all_ro = telekom.fetch(city_filter=parse_city_filter(["all"]))
    assert [j["id"] for j in all_ro] == ["1", "2", "3", "4"]
```

3. Update `tests/test_rinf.py`:
- Keep sidebar HTML fixture containing checkboxes (`name="city-bucharest"/><span ...>Bucharest<span...`, `name="city-timisoara"/><span ...>Timisoara<span...`, `name="city-cluj-napoca"/><span ...>Cluj-Napoca<span...`, `name="city-detroit"/><span ...>Detroit<span...`).
- Update `test_rinf_unescapes_titles_and_stops_when_page_repeats` to serve the sidebar HTML on the initial `/` request and job cards on `city=Timisoara`.
- Add `test_rinf_multi_city_alias_matching_and_dedup_merges_locations`: `city_filter=parse_city_filter(["timisoara,cluj"])` matches `"Timisoara"` and `"Cluj-Napoca"` (ignoring `"Bucharest"` and `"Detroit"`), and when job `"101"` appears in both cities, asserts a single job with `"location": "Timisoara; Cluj-Napoca"`.
- Add `test_rinf_unlisted_city_returns_empty_when_sidebar_present`: `city_filter=parse_city_filter(["arad"])` returns `[]` without paginating any city.
- Add `test_rinf_all_uses_country_romania`: `city_filter=parse_city_filter(["all"])` requests `country=Romania` (not `city=...`) and stamps `"location": "Romania"`.
- Add `test_rinf_raises_when_sidebar_has_no_city_checkboxes`: landing page without any `name="city-..."` markup raises `ValueError`.

4. Update `tests/test_successfactors.py`:
- Keep existing tests (both still pass because default queries `("Timisoara", "Romania")` and deduplicates by job ID).
- Add `test_successfactors_queries_all_search_terms_and_deduplicates`: with `city_filter=parse_city_filter(["bucharest"])`, asserts requests are made with `keywords` in `["Bucharest", "Bucuresti", "Romania"]`, overlapping job IDs across feeds are emitted once preserving first-seen order, and both `(Bucharest, RO)` and `(Bucuresti, RO)` plus `(Romania)` match while `(Timisoara, RO)` is dropped.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_beesite.py tests/test_telekom.py tests/test_rinf.py tests/test_successfactors.py -q`
Expected: FAIL (`TypeError` on `city_filter` / old hardcoded queries)

- [ ] **Step 3: Implement updates in `beesite.py`, `telekom.py`, `rinf.py`, `successfactors.py`, `state.py`, and `tests/test_state.py`**

- `beesite.py`: add `city_filter: CityFilter = DEFAULT_CITY_FILTER` to `fetch_porsche`; drop `PositionLocation.City` from `SearchCriteria`; extract `city = ((d.get("PositionLocation") or [{}])[0].get("CityName") or "").strip()`; keep when `city_filter.is_all or city_filter.matches(city)`; set `"location": city`.
- `telekom.py`: add `city_filter: CityFilter = DEFAULT_CITY_FILTER` to `fetch`; query `params={"location": "Romania", "page": page}`; keep when `city_filter.is_all or city_filter.matches(p["city"])`.
- `rinf.py`: add `city_filter: CityFilter = DEFAULT_CITY_FILTER` to `fetch`; implement the two paths from the spec (`is_all` paginates `country=Romania` with `"location": "Romania"`; specific cities fetch `/` once, extract `name="city-..."` checkboxes with `re.findall(r'name="city-[^"]*"[^>]*>\s*<span[^>]*>([^<]+)<span', text)`, raise `ValueError("no city filters found on rinf.tech")` if empty, paginate each matched city tracking per-city seen IDs so repeating pages stop cleanly, and merge into a cross-city dict by job ID appending `city_name` to `"; "`-joined `"location"` only when not already present).
- `successfactors.py`: add `city_filter: CityFilter = DEFAULT_CITY_FILTER` to `fetch`; iterate `kw` in `city_filter.search_terms()`, sanitize raw `&`, parse items, match `city_filter.matches(location)`, deduplicate by `job_id` preserving first-seen order.
- `state.py`: remove `matches_timisoara` and unused `import unicodedata`.
- `tests/test_state.py`: remove `matches_timisoara` import and the two parametrized location tests (now covered by `tests/test_cities.py`), keeping all `collect_results` tests.

- [ ] **Step 4: Run full test suite, lint, and typecheck**

Run: `uv run pytest -q && uv run pyrefly check && uv run ruff check src tests`
Expected: PASS (all tests green, 0 pyrefly errors, 0 ruff errors)

- [ ] **Step 5: Commit**

```bash
git add src/job_radar/sources/beesite.py src/job_radar/sources/telekom.py src/job_radar/sources/rinf.py src/job_radar/sources/successfactors.py src/job_radar/state.py tests/test_beesite.py tests/test_telekom.py tests/test_rinf.py tests/test_successfactors.py tests/test_state.py
git commit -m "feat: generalize beesite, telekom, rinf, and successfactors city filtering"
```

---

### Task 4: Wire `--city` CLI, `Fetcher` protocol, email subject prefix, GitHub Actions, and docs

**Files:**
- Modify: `src/job_radar/sources/__init__.py`, `src/job_radar/mailer.py`, `src/job_radar/runner.py`, `src/job_radar/__init__.py`, `.github/workflows/check.yml`, `README.md`
- Modify: `tests/test_mailer.py`, `tests/test_run.py`

**Interfaces:**
- Consumes: `CityFilter`, `DEFAULT_CITY_FILTER`, `parse_city_filter` from `job_radar.cities`; updated fetchers from `job_radar.sources.*`.
- Produces:
  - `sources.Fetcher` `Protocol`: `def __call__(self, *, city_filter: CityFilter = ...) -> list[dict]: ...`
  - `sources.FETCHERS: dict[str, Fetcher]`
  - `mailer.format_email(tiered_jobs: dict[str, list[dict]], notes: list[str], city_label: str = "") -> tuple[str, str] | None`
  - `runner.run(fetchers: Mapping[str, Fetcher], send: Callable[[str, str], None], city_filter: CityFilter = DEFAULT_CITY_FILTER) -> int`
  - CLI: `uv run python -m job_radar [--dry-run] [--city CITY ...]`

- [ ] **Step 1: Update and add failing tests in `tests/test_mailer.py` and `tests/test_run.py`**

1. In `tests/test_mailer.py`:
- Keep existing unprefixed assertions (since `city_label=""` is the default).
- Add `test_email_prefixes_subject_with_city_label`:
  - `format_email({"best": [job("1", "Nokia")], "other": [job("2", "Bosch")]}, [], city_label="Timișoara, Cluj-Napoca")` → subject `"[Timișoara, Cluj-Napoca] 1 best, 1 other jobs: Bosch, Nokia"`.
  - `format_email({"best": [job("1", "Nokia")], "other": []}, [], city_label="Romania")` → subject `"[Romania] 1 best job: Nokia"`.
  - `format_email({}, ["Haufe check broke: boom"], city_label="Cluj-Napoca")` → subject `"[Cluj-Napoca] job alert: Haufe check broke: boom"`.
  - `format_email({}, [], city_label="Timișoara")` → `None`.

2. In `tests/test_run.py`:
- Update existing stub fetchers to accept `city_filter=DEFAULT_CITY_FILTER` (e.g. `def boom(*, city_filter=DEFAULT_CITY_FILTER)` and `lambda *, city_filter=DEFAULT_CITY_FILTER: [...]`), and update expected subjects to include `[Timișoara] ` prefix.
- Update `test_main_loads_dotenv_before_running` so `fake_run(fetchers, send, city_filter=...)` checks `city_filter == DEFAULT_CITY_FILTER`.
- Add `test_run_passes_custom_city_filter_to_fetchers_and_email`: passes `parse_city_filter(["timisoara,cluj"])` to `run(...)`, asserts each fetcher receives that exact `CityFilter`, stdout logs `"cities: Timișoara, Cluj-Napoca"`, and email subject starts with `"[Timișoara, Cluj-Napoca] "`.
- Add `test_main_parses_city_flags_and_rejects_blank`:
  - `["job_radar", "--dry-run", "--city", "timisoara,cluj", "--city", "bucuresti"]` passes `parse_city_filter(["timisoara,cluj,bucharest"])` to `run`.
  - `["job_radar", "--dry-run", "--city", "all"]` passes `is_all=True` (`label == "Romania"`).
  - `["job_radar", "--dry-run", "--city", " , "]` exits via `pytest.raises(SystemExit)` with `exc.value.code == 2` and does not call `run`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mailer.py tests/test_run.py -q`
Expected: FAIL (`TypeError` on `city_label` / `city_filter`, unrecognized `--city`)

- [ ] **Step 3: Implement changes in `sources/__init__.py`, `mailer.py`, `runner.py`, `__init__.py`, `.github/workflows/check.yml`, and `README.md`**

- `src/job_radar/sources/__init__.py`: define `Fetcher(Protocol)` with `def __call__(self, *, city_filter: CityFilter = ...) -> list[dict]: ...` and type `FETCHERS: dict[str, Fetcher]`.
- `src/job_radar/mailer.py`: add `city_label: str = ""` parameter to `format_email`; when `city_label` is non-empty, prefix `subject` with `f"[{city_label}] "` before whitespace collapse.
- `src/job_radar/runner.py`:
  - Update `run(fetchers: Mapping[str, Fetcher], send: Callable[[str, str], None], city_filter: CityFilter = DEFAULT_CITY_FILTER) -> int` to print `f"cities: {city_filter.label}"`, submit `pool.submit(fetch, city_filter=city_filter)`, and call `format_email(tiered_jobs, notes, city_label=city_filter.label)`.
  - In `main()`, add `--city` (`action="append"`, `metavar="CITY"`), parse via `parse_city_filter(args.city)` catching `ValueError` with `parser.error(str(e))`, and call `run(FETCHERS, send, city_filter=city_filter)`.
- `src/job_radar/__init__.py`: update module docstring to `"Check employers' careers APIs for Romanian jobs (default: Timișoara) and email the current offers."`.
- `.github/workflows/check.yml`: add `workflow_dispatch.inputs.city` (optional string, default `""`), set `CITIES: ${{ inputs.city || vars.CITIES }}` in `env:`, and run `uv run --locked python -m job_radar --city "$CITIES"` when `"$CITIES"` is non-empty else `uv run --locked python -m job_radar`.
- `README.md`: document `--city` usage examples (`--city timisoara,cluj`, `--city all`), `vars.CITIES` / workflow dispatch override, and `cities.py` in Layout.

- [ ] **Step 4: Run full verification suite**

Run: `uv run pytest -v && uv run pyrefly check && uv run ruff check src tests && uv run ruff format --check src tests`
Expected: PASS (all tests pass, 0 pyrefly errors, 0 ruff lint/format issues)

- [ ] **Step 5: Commit**

```bash
git add src/job_radar/sources/__init__.py src/job_radar/mailer.py src/job_radar/runner.py src/job_radar/__init__.py .github/workflows/check.yml README.md tests/test_mailer.py tests/test_run.py
git commit -m "feat: wire --city CLI flag, email subject label, and workflow config"
```
