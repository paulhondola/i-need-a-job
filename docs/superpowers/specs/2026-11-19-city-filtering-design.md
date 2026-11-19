# Flag-Based Romanian City Filtering — Design Spec

Date: 2026-11-19

## Intent

`job_radar` currently hardcodes Timișoara in two places: a single client-side matcher (`matches_timisoara()` in `state.py`) and server-side query parameters across four fetchers (`beesite.py`, `rinf.py`, `successfactors.py`, `telekom.py`). All 25 tracked companies in `sources/__init__.py` are zero-argument callables, so checking openings in another Romanian hub (e.g. Cluj-Napoca, Bucharest, Iași) or across multiple hubs requires editing code.

This change introduces a CLI `--city` flag (supporting comma-separated or repeated Romanian cities, plus `--city all`, defaulting to Timișoara) backed by a stateless `CityFilter` value object passed explicitly to all fetchers.

**Constraints & agreed semantics:**
- Default behavior with no `--city` flag remains Timișoara (preserving backward-compatible daily digests).
- Bare `"Romania"` locations and Romania-remote roles continue to be included by default for maximum recall.
- The tracked company list in `sources/__init__.py`, `preferences.md`, and the regex/LLM filtering pipeline in `filter.py` remain unchanged.
- Email subjects reflect the active city filter, and `.github/workflows/check.yml` allows overriding cities via a repository variable (`vars.CITIES`) or a manual `workflow_dispatch` input while defaulting to Timișoara.

**Success:** Paul can run `uv run python -m job_radar --dry-run --city timisoara,cluj` (or `--city bucharest`, `--city all`, or an unlisted Romanian city) and receive accurately city-filtered, tiered results across all 11 source integrations, while daily scheduled runs continue targeting Timișoara unless `vars.CITIES` is configured.

## Architecture & Data Flow

```text
CLI (--city timisoara,cluj | --city all | omitted -> Timișoara)
  → parse_city_filter()                 # resolve Romanian hub catalog + fallback -> CityFilter (cities.py)
  → run(fetchers, send, city_filter)    # ThreadPoolExecutor invokes fetch(city_filter=city_filter) (runner.py)
  → collect_results()                   # deduplicate by job["id"] per source (state.py)
  → filter_jobs()                       # regex_prefilter() + llm_filter() (filter.py, unchanged)
  → format_email(..., city_label=...)   # prefix subject with [city_label] (mailer.py)
  → send_email() / --dry-run
```

## Module Specifications

### 1. `src/job_radar/cities.py` (new module)

Owns text normalization, the curated Romanian city catalog, CLI parsing, location matching, and server-side search keyword expansion.

#### Normalization & Catalog
- `fold(text: str) -> str`: NFKD-normalizes text, strips Unicode combining marks (`ș`/`ş` → `s`, `ț`/`ţ` → `t`, `ă`/`â` → `a`, `î` → `i`), applies `.casefold()`, and collapses whitespace via `" ".join(...split())`.
- `CitySpec` (`@dataclass(frozen=True)`):
  - `canonical: str` — display label used in email subjects and logs.
  - `aliases: tuple[str, ...]` — folded names accepted both in `--city` input and when matching job locations.
  - `search_terms: tuple[str, ...]` — ASCII search terms used by server-side keyword APIs (`successfactors.py`).
- Curated catalog (`ROMANIAN_CITIES: tuple[CitySpec, ...]`):

| `canonical` | `aliases` | `search_terms` |
|---|---|---|
| `Timișoara` | `("timisoara",)` | `("Timisoara",)` |
| `Bucharest` | `("bucharest", "bucuresti")` | `("Bucharest", "Bucuresti")` |
| `Cluj-Napoca` | `("cluj-napoca", "cluj")` | `("Cluj",)` |
| `Iași` | `("iasi",)` | `("Iasi",)` |
| `Brașov` | `("brasov",)` | `("Brasov",)` |
| `Sibiu` | `("sibiu",)` | `("Sibiu",)` |
| `Oradea` | `("oradea",)` | `("Oradea",)` |
| `Craiova` | `("craiova",)` | `("Craiova",)` |
| `Constanța` | `("constanta",)` | `("Constanta",)` |
| `Arad` | `("arad",)` | `("Arad",)` |
| `Ploiești` | `("ploiesti",)` | `("Ploiesti",)` |
| `Târgu Mureș` | `("targu mures", "tg mures", "tg. mures")` | `("Targu Mures",)` |
| `Pitești` | `("pitesti",)` | `("Pitesti",)` |
| `Galați` | `("galati",)` | `("Galati",)` |
| `Bacău` | `("bacau",)` | `("Bacau",)` |

- Catalog lookup normalizes hyphens and whitespace identically (`re.sub(r"[-\s]+", " ", fold(token))`) so `--city cluj-napoca`, `--city "cluj napoca"`, `--city cluj`, and `--city targu-mures` all resolve to their canonical `CitySpec`.
- **Arbitrary fallback:** any unlisted city token produces a dynamic `CitySpec`:
  - `canonical`: stripped original token if it contains any uppercase character (e.g. `"Petroșani"` → `"Petroșani"`), otherwise `.title()` of the stripped token (e.g. `"alba iulia"` → `"Alba Iulia"`, `"baia-mare"` → `"Baia-Mare"`).
  - `aliases`: `(fold(token),)`.
  - `search_terms`: `(ascii_title,)` where `ascii_title` is the NFKD-stripped form of `canonical`.

#### `CityFilter` (`@dataclass(frozen=True)`)
- Fields:
  - `cities: tuple[CitySpec, ...]` — selected cities (empty when `is_all=True`).
  - `is_all: bool = False` — `True` for all-of-Romania mode (`--city all` or `--city romania`).
- `DEFAULT_CITY_FILTER`: `CityFilter(cities=(_TIMISOARA,))`.
- `label` property:
  - Returns `"Romania"` when `is_all=True`.
  - Otherwise returns `", ".join(c.canonical for c in self.cities)`.
- `matches(location: str) -> bool`:
  - Empty/blank `location` returns `False`.
  - Precompiled word-boundary regex per alias: split each alias on `[-\s]+`, `re.escape` each segment, join with `[-\s]+`, and wrap in `(?<!\w)...(?!\w)` against `fold(location)`. This avoids substring false positives (e.g. `"arad"` will not match `"Colorado"`) while matching hyphen/space variants (`"Cluj-Napoca"` / `"Cluj Napoca"`) and structured location strings (`"TIMISOARA, TM, RO, 307160"`, `"Timisoara (Hybrid), RO"`).
  - Standalone country-code helper `_has_ro_code(location: str) -> bool`: checks `re.search(r"(?:^|[\s,(/-])RO(?:$|[\s,)/-])", location)` on the **original-case** string to match `"Cluj, RO"`, `"TIMISOARA, TM, RO, 307160"`, and `"Remote, RO"` without matching lowercase words.
  - When `is_all=False`: returns `True` if any of the following holds:
    1. Any selected city's alias pattern matches `fold(location)`.
    2. `fold(location) == "romania"` (bare country-only posting).
    3. Explicit Romania-remote: `fold(location)` contains word `remote` (`(?<!\w)remote(?!\w)`) AND (`fold(location)` contains word `romania` OR `_has_ro_code(location)` is `True`).
  - When `is_all=True`: returns `True` if any of the following holds:
    1. `fold(location)` contains word `romania`.
    2. `_has_ro_code(location)` is `True`.
    3. Any alias pattern in `ROMANIAN_CITIES` matches `fold(location)` (covers boards that emit bare city names like `"Cluj"` or `"Bucharest"` without a country suffix).
- `search_terms() -> tuple[str, ...]`:
  - When `is_all=False`: deduplicated (order-preserving) union of `c.search_terms` for each `c` in `self.cities`, followed by `"Romania"` (for bare-Romania/Romania-remote recall).
  - When `is_all=True`: `"Romania"` followed by the deduplicated union of `c.search_terms` across `ROMANIAN_CITIES`.

#### Parsing (`parse_city_filter(raw: list[str] | None) -> CityFilter`)
- `raw is None` → returns `DEFAULT_CITY_FILTER`.
- Splits every string in `raw` on `,`, strips whitespace, and discards empty segments.
- If no non-empty tokens remain (e.g. `--city ""` or `--city " , "`) → raises `ValueError("at least one city name is required")`.
- If any folded token is `"all"` or `"romania"` → returns `CityFilter(cities=(), is_all=True)` (subsuming individual cities if mixed, e.g. `--city timisoara,all`).
- Resolves each token via catalog or dynamic fallback and deduplicates by normalized lookup key (`re.sub(r"[-\s]+", " ", fold(spec.aliases[0]))`) preserving first-seen order (so `--city bucharest,bucuresti` and `--city baia-mare,"baia mare"` each collapse to a single entry).

### 2. `src/job_radar/state.py` (modified)

- Remove `matches_timisoara()`. `state.py` keeps only `collect_results(results: dict) -> tuple[list[dict], list[str]]`.

### 3. `src/job_radar/sources/` (all 11 modules + `__init__.py` modified)

#### Fetcher Protocol (`src/job_radar/sources/__init__.py`)
- Define a `Fetcher` `Protocol`:
  ```python
  class Fetcher(Protocol):
      def __call__(self, *, city_filter: CityFilter = ...) -> list[dict]: ...
  ```
- Type `FETCHERS: dict[str, Fetcher]`. Existing `partial(...)` entries remain one line per company because `runner.py` invokes them with keyword argument `city_filter=city_filter`.
- Every source's `fetch(...)` (and `beesite.fetch_porsche(...)`) adds `city_filter: CityFilter = DEFAULT_CITY_FILTER` as a trailing parameter with default `DEFAULT_CITY_FILTER` so direct calls in tests/REPL remain backward-compatible.

#### Per-Source Behavior

1. **Client-side filter sources (5 modules):**
   - `greenhouse.py`: `any(city_filter.matches(part) for part in loc.split(";"))`
   - `lever.py`: `any(city_filter.matches(loc) for loc in locations)`
   - `oracle.py`: `any(city_filter.matches(loc) for loc in locations)`
   - `personio.py`: `any(city_filter.matches(o) for o in offices)`
   - `teamtailor.py`: `any(city_filter.matches(c) for c in cities)`
2. **SmartRecruiters (`smartrecruiters.py`):**
   - Continues querying `country="ro"`.
   - Keeps posting when `p["location"].get("remote") or city_filter.is_all or city_filter.matches(p["location"].get("city") or "")`.
3. **Workday (`workday.py`):**
   - Matches dynamic location facets via `matched = [v for v in locations if city_filter.matches(v["descriptor"])]`.
   - Passes all matched facet IDs in `appliedFacets: {"locations": ids}`.
4. **Porsche Beesite (`beesite.py`):**
   - Removes `{"CriterionName": "PositionLocation.City", "CriterionValue": ["311"]}` from `SearchCriteria`, keeping `PositionLocation.Country: ["176"]` (Romania) and `PublicationChannel.Code: ["12"]`.
   - Strips `CityName` (`city = d["PositionLocation"][0]["CityName"].strip()`, handling trailing spaces such as `"Bucharest "`).
   - Keeps posting when `city_filter.is_all or city_filter.matches(city)`, storing the stripped `city` in `"location"`.
5. **Deutsche Telekom (`telekom.py`):**
   - Queries `params={"location": "Romania", "page": page}` instead of `location="Timișoara"`.
   - Keeps posting when `city_filter.is_all or city_filter.matches(p["city"])`.
6. **rinf.tech (`rinf.py`):**
   - When `city_filter.is_all`: paginates `https://jobs.rinf.tech/` with `params={"country": "Romania", "page": page}` until a page yields no new job IDs, setting `"location": "Romania"`.
   - When `not city_filter.is_all`:
     1. Fetches `https://jobs.rinf.tech/` once and extracts sidebar city labels via `re.findall(r'name="city-[^"]*"[^>]*>\s*<span[^>]*>([^<]+)<span', text)` (HTML-unescaped and stripped).
     2. Raises `ValueError("no city filters found on rinf.tech")` if zero checkboxes are parsed (failing loudly on markup redesign rather than silently returning `[]`).
     3. Keeps discovered cities where `city_filter.matches(city_name)`. If none match the requested city, returns `[]`.
     4. For each matched city name, paginates `params={"city": city_name, "page": page}` until a page adds no new job IDs for that city. Deduplicates across matched cities by job ID; if the same job appears under multiple matched cities, appends the new city to its `"; "`-joined `"location"` field.
7. **SAP SuccessFactors (`successfactors.py`):**
   - Iterates `kw` in `city_filter.search_terms()`, querying `params={"locale": "en_US", "keywords": kw, "rows": 500}` and sanitizing raw `&` entities before XML parsing.
   - Extracts `(name, location)` from each item's title as today; keeps items where `city_filter.matches(location)`.
   - Deduplicates across keyword queries by extracted `job_id` (preserving first-seen order).

### 4. `src/job_radar/mailer.py` (modified)

- Signature becomes `format_email(tiered_jobs: dict[str, list[dict]], notes: list[str], city_label: str = "") -> tuple[str, str] | None`.
- When `city_label` is non-empty, prefixes the constructed subject with `f"[{city_label}] "` (before collapsing whitespace via `" ".join(subject.split())`):
  - Both tiers: `"[Timișoara, Cluj-Napoca] 2 best, 3 other jobs: Bosch, Nokia"`
  - Single tier: `"[Timișoara] 1 best job: Nokia"` / `"[Romania] 4 jobs: EY, OPSWAT"`
  - Notes only: `"[Cluj-Napoca] job alert: Haufe check broke: boom"`
- When `city_label == ""`, preserves existing unprefixed subject format.
- Email body layout is unchanged.

### 5. `src/job_radar/runner.py` & `src/job_radar/__init__.py` (modified)

- `run(fetchers: Mapping[str, Fetcher], send: Callable[[str, str], None], city_filter: CityFilter = DEFAULT_CITY_FILTER) -> int`:
  - Prints `f"cities: {city_filter.label}"`.
  - Submits `pool.submit(fetch, city_filter=city_filter)` for each source.
  - Passes `city_label=city_filter.label` to `format_email(tiered_jobs, notes, city_label=city_filter.label)`.
- `main() -> int`:
  - Adds `--city` (`action="append"`, `metavar="CITY"`, help explaining comma-separated/repeated cities, `all`, and Timișoara default).
  - Parses `city_filter = parse_city_filter(args.city)`, calling `parser.error(str(e))` on `ValueError`.
  - Passes `city_filter=city_filter` to `run(FETCHERS, send, city_filter=city_filter)`.
- Update `src/job_radar/__init__.py` package docstring to mention Romanian cities (defaulting to Timișoara).

### 6. `.github/workflows/check.yml` & `README.md` (modified)

- In `.github/workflows/check.yml`:
  - Add `workflow_dispatch.inputs.city` (optional string, default `""`, description `"Comma-separated Romanian cities or 'all' (overrides CITIES variable)"`).
  - Pass `CITIES: ${{ inputs.city || vars.CITIES }}` via `env:` and invoke `uv run --locked python -m job_radar --city "$CITIES"` when `"$CITIES"` is non-empty, else `uv run --locked python -m job_radar`.
- In `README.md`:
  - Document `--city` CLI usage (`--city timisoara,cluj`, `--city all`), the `cities.py` module in Layout, and the `CITIES` repository variable / manual dispatch override.

## Error Handling & Edge Cases

- **Blank `--city` value** (`--city ""` or `--city ","`): `parse_city_filter()` raises `ValueError`; `main()` exits via `parser.error(...)` with status 2 before making any network calls.
- **Duplicate / aliased cities** (`--city bucharest,bucuresti`, `--city cluj --city Cluj-Napoca`): collapsed to a single canonical `CitySpec` without duplicate queries or duplicate labels.
- **Mixed `all` and city names** (`--city timisoara,all`): `"all"` (or `"romania"`) subsumes individual cities into `is_all=True` with label `"Romania"`.
- **Unlisted Romanian city** (`--city alba-iulia`): handled by dynamic fallback `CitySpec`; sources with no openings there return `[]` without error notes.
- **rinf.tech HTML redesign** (zero `name="city-..."` checkboxes found): raises `ValueError`, caught by `runner.py` and surfaced as `"rinf.tech check broke: no city filters found on rinf.tech"` without halting other sources.
- **SuccessFactors keyword failure**: an HTTP/parse error on any keyword propagates out of that host's fetcher, caught by `runner.py` and recorded as `"<source> check broke: ..."`.
- **Trailing whitespace in Beesite `CityName`** (`"Bucharest "`): stripped before matching and storing in `job["location"]`.

## Testing Strategy

All unit tests run offline via `uv run pytest`, alongside `uv run ruff check`, `uv run ruff format --check`, and `uv run pyrefly check`:

- **`tests/test_cities.py` (new):**
  - `fold()` across Romanian diacritics (`ș`/`ş`, `ț`/`ţ`, `ă`/`â`/`î`), case, and whitespace.
  - `parse_city_filter()`: default (`None`), single city, comma-separated, repeated `--city`, hyphen/space normalization, alias deduplication (`bucharest,bucuresti`, `cluj,Cluj-Napoca`), `all`/`romania` subsumption, arbitrary fallback city, blank-input `ValueError`.
  - `CityFilter.matches()`: word-boundary safety (`arad` rejects `"Colorado"`), English/Romanian alias matching (`Bucharest` matches `"Bucuresti, RO"`), bare `"Romania"` and explicit Romania-remote (`"Remote - Romania"`, `"Remote, RO"`) accepted while `"EMEA - Remote"` and other cities (`"Bucharest, Romania"` for Timișoara) are rejected; `is_all` matches `"Romania"`, `", RO"`, and bare catalog city names (`"Cluj"`, `"Bucharest"`) while rejecting foreign locations (`"Budapest, Hungary"`).
  - `CityFilter.search_terms()`: deduplicated ASCII terms + `"Romania"` for specific cities; `"Romania"` + all catalog terms for `all`.
- **`tests/test_beesite.py` (new):**
  - Verifies `SearchCriteria` omits `PositionLocation.City` and keeps `Country=176`, strips trailing whitespace in `CityName`, and filters single-city, multi-city, and `all`.
- **`tests/test_telekom.py` (new):**
  - Verifies `location=Romania` pagination and filtering for single-city, multi-city, bare `"Romania"`, and `all`.
- **`tests/test_rinf.py` (updated):**
  - Verifies sidebar city checkbox discovery and alias matching (`Cluj` → `Cluj-Napoca`), multi-city pagination and ID deduplication with combined locations, empty return when no checkbox matches an unlisted city, `is_all` using `country=Romania`, and `ValueError` when sidebar markup contains zero city checkboxes.
- **`tests/test_successfactors.py` (updated):**
  - Verifies querying each term in `city_filter.search_terms()` (e.g. `Bucharest`, `Bucuresti`, `Romania`), deduplicating overlapping IDs, and filtering parenthesized locations for both default Timișoara and other cities.
- **`tests/test_greenhouse.py`, `tests/test_oracle.py`, `tests/test_smartrecruiters.py`, `tests/test_workday.py` (updated):**
  - Preserve existing Timișoara coverage and add cases with non-default `CityFilter` (e.g. Bucharest, multi-city, `all`).
- **`tests/test_state.py` (updated):**
  - Retains `collect_results()` coverage after moving location matching tests to `test_cities.py`.
- **`tests/test_mailer.py` & `tests/test_run.py` (updated):**
  - Verifies `[city_label]` subject prefixing (and unprefixed default when `city_label=""`), `--city` CLI parsing (default, comma-separated, repeated, `all`, invalid blank input exit code 2), and `city_filter` propagation through `run()` into fetchers and `format_email()`.
