import os

import pytest
from helpers import job

from job_radar.runner import load_dotenv, run


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    for var in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)


def boom():
    raise RuntimeError("down")


def test_run_filters_and_tiers_jobs(monkeypatch):
    monkeypatch.setattr(
        "job_radar.runner.filter_jobs",
        lambda jobs: ({"best": [job("1", "OPSWAT")], "other": [job("2", "Nokia")]}, []),
    )
    sent = []
    fetchers = {
        "OPSWAT": lambda: [job("1", "OPSWAT")],
        "Nokia": lambda: [job("2", "Nokia")],
    }
    assert run(fetchers, lambda s, b: sent.append((s, b))) == 0
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


def test_load_dotenv_sets_missing_and_preserves_existing(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "\n"
        "LLM_API_KEY=from-dotenv\n"
        'export LLM_MODEL="quoted-model"\n'
        "EXISTING_VAR=from-dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING_VAR", "from-shell")

    load_dotenv(env_file)

    assert os.environ["LLM_API_KEY"] == "from-dotenv"
    assert os.environ["LLM_MODEL"] == "quoted-model"
    assert os.environ["EXISTING_VAR"] == "from-shell"


def test_load_dotenv_ignores_missing_file(tmp_path):
    load_dotenv(tmp_path / "missing.env")
