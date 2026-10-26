import json

from helpers import job
from job_radar.runner import run

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
