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

from email.message import EmailMessage

def test_email_subject_is_single_line_for_multiline_errors():
    note = "Haufe check broke: Client error '403 Forbidden' for url 'x'\nFor more information check: y"
    subject, body = format_email({}, [note])
    assert "\n" not in subject
    EmailMessage()["Subject"] = subject  # raises ValueError on a linefeed
    assert "For more information check: y" in body
