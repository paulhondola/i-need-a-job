from helpers import job
from job_radar.runner import run

def boom():
    raise RuntimeError("down")

def test_run_emails_all_current_jobs():
    sent = []
    assert run({"OPSWAT": lambda: [job("1", "OPSWAT"), job("2", "OPSWAT")]}, lambda s, b: sent.append((s, b))) == 0
    assert len(sent) == 1
    assert sent[0][0] == "2 jobs: OPSWAT"
    assert "T1" in sent[0][1] and "T2" in sent[0][1]

def test_run_one_source_raising_does_not_stop_others():
    sent = []
    assert run({"Haufe": boom, "OPSWAT": lambda: [job("2", "OPSWAT")]}, lambda s, b: sent.append((s, b))) == 0
    assert len(sent) == 1
    subject, body = sent[0]
    assert subject == "1 job: OPSWAT"
    assert "T2" in body
    assert "Haufe check broke: down" in body

def test_run_smtp_failure_exits_nonzero():
    def bad_send(s, b):
        raise OSError("smtp down")
    assert run({"OPSWAT": lambda: [job("2")]}, bad_send) != 0

def test_run_nothing_to_send():
    sent = []
    assert run({"OPSWAT": lambda: []}, lambda s, b: sent.append(s)) == 0
    assert sent == []

