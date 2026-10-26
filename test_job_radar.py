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
