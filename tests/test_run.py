import pytest
from helpers import job

from job_radar.cities import DEFAULT_CITY_FILTER, CityFilter, parse_city_filter
from job_radar.runner import main, run


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    for var in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)


def boom(*, city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]:
    raise RuntimeError("down")


def test_run_filters_and_tiers_jobs(monkeypatch):
    received = []

    def fake_filter_jobs(jobs):
        received.append(jobs)
        return {"best": [job("1", "OPSWAT")], "other": [job("2", "Nokia")]}, []

    monkeypatch.setattr("job_radar.runner.filter_jobs", fake_filter_jobs)
    sent = []
    fetchers = {
        "OPSWAT": lambda *, city_filter=DEFAULT_CITY_FILTER: [job("1", "OPSWAT")],
        "Nokia": lambda *, city_filter=DEFAULT_CITY_FILTER: [job("2", "Nokia")],
    }
    assert run(fetchers, lambda s, b: sent.append((s, b))) == 0
    assert received == [[job("1", "OPSWAT"), job("2", "Nokia")]]
    assert len(sent) == 1
    subject, body = sent[0]
    assert subject == "[Timișoara] 1 best, 1 other jobs: Nokia, OPSWAT"
    assert "=== BEST MATCHES (1) ===" in body
    assert "=== OTHER TECH ROLES (1) ===" in body


def test_run_falls_back_when_llm_key_missing(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    sent = []
    assert (
        run(
            {
                "OPSWAT": lambda *, city_filter=DEFAULT_CITY_FILTER: [
                    job("1", "OPSWAT"),
                    {**job("2", "OPSWAT"), "title": "Senior HR Manager"},
                ]
            },
            lambda s, b: sent.append((s, b)),
        )
        == 0
    )
    assert len(sent) == 1
    subject, body = sent[0]
    assert subject == "[Timișoara] 1 job: OPSWAT"
    assert "T1" in body and "Senior HR Manager" not in body
    assert "llm filter broke:" in body


def test_run_one_source_raising_does_not_stop_others(monkeypatch):
    monkeypatch.setattr(
        "job_radar.runner.filter_jobs",
        lambda jobs: ({"best": [job("2", "OPSWAT")], "other": []}, []),
    )
    sent = []
    assert (
        run(
            {
                "Haufe": boom,
                "OPSWAT": lambda *, city_filter=DEFAULT_CITY_FILTER: [
                    job("2", "OPSWAT")
                ],
            },
            lambda s, b: sent.append((s, b)),
        )
        == 0
    )
    assert len(sent) == 1
    subject, body = sent[0]
    assert subject == "[Timișoara] 1 best job: OPSWAT"
    assert "T2" in body
    assert "Haufe check broke: down" in body


def test_run_smtp_failure_exits_nonzero(monkeypatch):
    monkeypatch.setattr(
        "job_radar.runner.filter_jobs",
        lambda jobs: ({"best": [job("2")], "other": []}, []),
    )

    def bad_send(s, b):
        raise OSError("smtp down")

    assert (
        run(
            {"OPSWAT": lambda *, city_filter=DEFAULT_CITY_FILTER: [job("2")]},
            bad_send,
        )
        != 0
    )


def test_run_nothing_to_send(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    sent = []
    assert (
        run(
            {"OPSWAT": lambda *, city_filter=DEFAULT_CITY_FILTER: []},
            lambda s, b: sent.append(s),
        )
        == 0
    )
    assert sent == []


def test_run_passes_custom_city_filter_to_fetchers_and_email(monkeypatch, capsys):
    monkeypatch.setattr(
        "job_radar.runner.filter_jobs",
        lambda jobs: ({"best": jobs, "other": []}, []),
    )
    target_filter = parse_city_filter(["timisoara,cluj"])
    seen_filters: list[CityFilter] = []
    sent = []

    def fetcher(*, city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]:
        seen_filters.append(city_filter)
        return [job("1", "OPSWAT")]

    assert (
        run(
            {"OPSWAT": fetcher},
            lambda s, b: sent.append((s, b)),
            city_filter=target_filter,
        )
        == 0
    )
    assert seen_filters == [target_filter]
    assert "cities: Timișoara, Cluj-Napoca" in capsys.readouterr().out
    assert sent[0][0] == "[Timișoara, Cluj-Napoca] 1 best job: OPSWAT"


def test_main_loads_dotenv_before_running(monkeypatch):
    events = []
    seen_filters = []

    def fake_run(fetchers, send, city_filter=DEFAULT_CITY_FILTER):
        events.append("run")
        seen_filters.append(city_filter)
        return 0

    monkeypatch.setattr("sys.argv", ["job_radar", "--dry-run"])
    monkeypatch.setattr("job_radar.runner.load_dotenv", lambda: events.append("dotenv"))
    monkeypatch.setattr("job_radar.runner.run", fake_run)

    assert main() == 0
    assert events == ["dotenv", "run"]
    assert seen_filters == [DEFAULT_CITY_FILTER]


def test_main_parses_city_flags_and_rejects_blank(monkeypatch):
    seen_filters: list[CityFilter] = []

    def fake_run(fetchers, send, city_filter=DEFAULT_CITY_FILTER):
        seen_filters.append(city_filter)
        return 0

    monkeypatch.setattr("job_radar.runner.load_dotenv", lambda: None)
    monkeypatch.setattr("job_radar.runner.run", fake_run)

    monkeypatch.setattr(
        "sys.argv",
        ["job_radar", "--dry-run", "--city", "timisoara,cluj", "--city", "bucuresti"],
    )
    assert main() == 0
    assert seen_filters[-1] == parse_city_filter(["timisoara,cluj,bucharest"])

    monkeypatch.setattr("sys.argv", ["job_radar", "--dry-run", "--city", "all"])
    assert main() == 0
    assert seen_filters[-1].is_all
    assert seen_filters[-1].label == "Romania"

    count_before = len(seen_filters)
    monkeypatch.setattr("sys.argv", ["job_radar", "--dry-run", "--city", " , "])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert len(seen_filters) == count_before
