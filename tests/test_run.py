import pytest
from helpers import job

from job_radar.runner import main, run


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    for var in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)


def boom():
    raise RuntimeError("down")


def test_run_filters_and_tiers_jobs(monkeypatch):
    received = []

    def fake_filter_jobs(jobs):
        received.append(jobs)
        return {"best": [job("1", "OPSWAT")], "other": [job("2", "Nokia")]}, []

    monkeypatch.setattr("job_radar.runner.filter_jobs", fake_filter_jobs)
    sent = []
    fetchers = {
        "OPSWAT": lambda: [job("1", "OPSWAT")],
        "Nokia": lambda: [job("2", "Nokia")],
    }
    assert run(fetchers, lambda s, b: sent.append((s, b))) == 0
    assert received == [[job("1", "OPSWAT"), job("2", "Nokia")]]
    assert len(sent) == 1
    subject, body = sent[0]
    assert subject == "1 best, 1 other jobs: Nokia, OPSWAT"
    assert "=== BEST MATCHES (1) ===" in body
    assert "=== OTHER TECH ROLES (1) ===" in body


def test_run_falls_back_when_llm_key_missing(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    sent = []
    assert (
        run(
            {
                "OPSWAT": lambda: [
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
    assert subject == "1 job: OPSWAT"
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
            {"Haufe": boom, "OPSWAT": lambda: [job("2", "OPSWAT")]},
            lambda s, b: sent.append((s, b)),
        )
        == 0
    )
    assert len(sent) == 1
    subject, body = sent[0]
    assert subject == "1 best job: OPSWAT"
    assert "T2" in body
    assert "Haufe check broke: down" in body


def test_run_smtp_failure_exits_nonzero(monkeypatch):
    monkeypatch.setattr(
        "job_radar.runner.filter_jobs",
        lambda jobs: ({"best": [job("2")], "other": []}, []),
    )

    def bad_send(s, b):
        raise OSError("smtp down")

    assert run({"OPSWAT": lambda: [job("2")]}, bad_send) != 0


def test_run_nothing_to_send(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    sent = []
    assert run({"OPSWAT": list}, lambda s, b: sent.append(s)) == 0
    assert sent == []


def test_main_loads_dotenv_before_running(monkeypatch):
    events = []

    def fake_run(fetchers, send):
        events.append("run")
        return 0

    monkeypatch.setattr("sys.argv", ["job_radar", "--dry-run"])
    monkeypatch.setattr("job_radar.runner.load_dotenv", lambda: events.append("dotenv"))
    monkeypatch.setattr("job_radar.runner.run", fake_run)

    assert main() == 0
    assert events == ["dotenv", "run"]
