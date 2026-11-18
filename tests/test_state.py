import pytest

from helpers import job
from job_radar.state import collect_results, matches_timisoara

@pytest.mark.parametrize("loc", ["Timișoara", "Timişoara", "Timisoara", "TIMISOARA",
    "Timișoara, Timiș, Romania", "Romania, Timisoara", "Romania", " romania "])
def test_location_matches(loc):
    assert matches_timisoara(loc)

@pytest.mark.parametrize("loc", ["Romania, Bucharest", "Cluj-Napoca, Romania",
    "Budapest, Hungary", "EMEA - Remote", ""])
def test_location_rejects(loc):
    assert not matches_timisoara(loc)

def test_collects_all_jobs():
    jobs, notes = collect_results({"OPSWAT": [job("1"), job("2")]})
    assert [j["id"] for j in jobs["OPSWAT"]] == ["1", "2"]
    assert notes == []

def test_int_ids_normalized_to_str():
    jobs, _ = collect_results({"OPSWAT": [job(4738830005)]})
    assert jobs["OPSWAT"][0]["id"] == "4738830005"

def test_duplicate_ids_in_one_fetch_deduplicated():
    jobs, _ = collect_results({"Nokia": [job("7"), job("7")]})
    assert len(jobs["Nokia"]) == 1

def test_failure_recorded_in_notes():
    jobs, notes = collect_results({"Haufe": RuntimeError("key expired"), "OPSWAT": [job("1")]})
    assert "Haufe" not in jobs
    assert [j["id"] for j in jobs["OPSWAT"]] == ["1"]
    assert notes == ["Haufe check broke: key expired"]

def test_empty_result_omitted_and_not_broken():
    jobs, notes = collect_results({"Intel": []})
    assert (jobs, notes) == ({}, [])

