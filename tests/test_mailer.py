from email.message import EmailMessage

from helpers import job
from job_radar.mailer import format_email

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

def test_email_subject_is_single_line_for_multiline_errors():
    note = "Haufe check broke: Client error '403 Forbidden' for url 'x'\nFor more information check: y"
    subject, body = format_email({}, [note])
    assert "\n" not in subject
    EmailMessage()["Subject"] = subject  # raises ValueError on a linefeed
    assert "For more information check: y" in body
