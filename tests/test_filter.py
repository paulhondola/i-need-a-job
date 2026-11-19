import httpx
import pytest

from helpers import job
from job_radar.filter import DEFAULT_PREFERENCES_PATH, filter_jobs, llm_filter, regex_prefilter


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    for var in ("GROQ_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)


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
    "Data Warehouse Engineer",
    "Domain Controller Software Engineer",
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
    "Warehouse Manager",
    "Mechanical Design Engineer",
    "Manufacturing Engineer",
    "IT Support Specialist with German",
    "Helpdesk Analyst (German Speaker)",
])
def test_regex_prefilter_drops_excluded_roles(title):
    assert regex_prefilter([titled_job("1", title)]) == []


def test_llm_filter_empty_jobs_skips_http():
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


def test_filter_jobs_zero_survivors_skips_llm_and_preferences(tmp_path, capsys):
    j_drop = titled_job("1", "Senior HR Manager", "Nokia")

    tiered, notes = filter_jobs({"Nokia": [j_drop]}, preferences_path=tmp_path / "missing.md")
    assert tiered == {"best": [], "other": []}
    assert notes == []
    assert "filter: 1 total -> 0 after regex -> 0 best, 0 other" in capsys.readouterr().out


def test_filter_jobs_fallback_when_api_key_missing(capsys):
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


@pytest.mark.parametrize("content", [
    '{"error": "rate limit"}',
    '{"best_matches": [0]}',
    '{"best": "0, 1", "other": "2"}',
])
def test_filter_jobs_fallback_on_wrong_schema_json(monkeypatch, content):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def fake_post(url, *, headers, json, timeout):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
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
