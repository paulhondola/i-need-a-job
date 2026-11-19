from helpers import job

from job_radar.state import collect_results


def test_collects_all_jobs():
    jobs, notes = collect_results({"OPSWAT": [job("1"), job("2")]})
    assert [j["id"] for j in jobs] == ["1", "2"]
    assert notes == []


def test_int_ids_normalized_to_str():
    jobs, _ = collect_results({"OPSWAT": [job(4738830005)]})
    assert jobs[0]["id"] == "4738830005"


def test_duplicate_ids_in_one_fetch_deduplicated():
    jobs, _ = collect_results({"Nokia": [job("7"), job("7")]})
    assert len(jobs) == 1


def test_failure_recorded_in_notes():
    jobs, notes = collect_results(
        {"Haufe": RuntimeError("key expired"), "OPSWAT": [job("1")]}
    )
    assert [j["id"] for j in jobs] == ["1"]
    assert notes == ["Haufe check broke: key expired"]


def test_failure_with_empty_exception_message_uses_class_name():
    jobs, notes = collect_results({"Intel": StopIteration()})
    assert jobs == []
    assert notes == ["Intel check broke: StopIteration"]


def test_empty_result_omitted_and_not_broken():
    jobs, notes = collect_results({"Intel": []})
    assert (jobs, notes) == ([], [])
