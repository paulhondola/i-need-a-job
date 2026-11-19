from email.message import EmailMessage

from helpers import job

from job_radar.mailer import format_email


def _format_present(
    tiered_jobs: dict[str, list[dict]], notes: list[str]
) -> tuple[str, str]:
    email = format_email(tiered_jobs, notes)
    assert email is not None
    return email


def test_email_nothing_to_say():
    assert format_email({}, []) is None
    assert format_email({"best": [], "other": []}, []) is None


def test_email_renders_both_tiers_grouped_by_company():
    tiered = {
        "best": [job("1", "OPSWAT"), job("2", "Nokia")],
        "other": [job("3", "Porsche Engineering"), job("4", "Bosch")],
    }
    subject, body = _format_present(tiered, [])
    assert subject == "2 best, 2 other jobs: Bosch, Nokia, OPSWAT, Porsche Engineering"
    assert "=== BEST MATCHES (2) ===" in body
    assert "=== OTHER TECH ROLES (2) ===" in body
    assert (
        body.index("=== BEST MATCHES (2) ===")
        < body.index("Nokia")
        < body.index("OPSWAT")
    )
    assert (
        body.index("OPSWAT")
        < body.index("=== OTHER TECH ROLES (2) ===")
        < body.index("Bosch")
        < body.index("Porsche Engineering")
    )


def test_email_best_only_singular_and_plural():
    subject, body = _format_present({"best": [job("1", "Nokia")], "other": []}, [])
    assert subject == "1 best job: Nokia"
    assert "=== BEST MATCHES (1) ===" in body
    assert "=== OTHER TECH ROLES" not in body

    subject2, _ = _format_present(
        {"best": [job("1", "Nokia"), job("2", "OPSWAT")], "other": []}, []
    )
    assert subject2 == "2 best jobs: Nokia, OPSWAT"


def test_email_other_only_singular_and_plural():
    subject, body = _format_present({"best": [], "other": [job("3", "OPSWAT")]}, [])
    assert subject == "1 job: OPSWAT"
    assert "=== OTHER TECH ROLES (1) ===" in body
    assert "=== BEST MATCHES" not in body

    subject2, _ = _format_present(
        {"best": [], "other": [job("1", "Nokia"), job("2", "OPSWAT")]}, []
    )
    assert subject2 == "2 jobs: Nokia, OPSWAT"


def test_email_notes_only():
    subject, body = _format_present(
        {"best": [], "other": []}, ["Haufe check broke: boom"]
    )
    assert subject == "job alert: Haufe check broke: boom"
    assert "Haufe check broke: boom" in body


def test_email_notes_after_jobs():
    _, body = _format_present(
        {"best": [job("3", "OPSWAT")], "other": []}, ["Haufe check broke: boom"]
    )
    assert body.index("T3") < body.index("Haufe check broke: boom")


def test_email_subject_is_single_line_for_multiline_errors():
    note = "llm filter broke: Client error '429 Too Many Requests' for url 'x'\nFor more information check: y"
    subject, body = _format_present({}, [note])
    assert "\n" not in subject
    EmailMessage()["Subject"] = subject
    assert "For more information check: y" in body


def test_email_prefixes_subject_with_city_label():
    subject, _ = _format_present(
        {"best": [job("1", "Nokia")], "other": [job("2", "Bosch")]},
        [],
    )
    assert subject == "1 best, 1 other jobs: Bosch, Nokia"

    email1 = format_email(
        {"best": [job("1", "Nokia")], "other": [job("2", "Bosch")]},
        [],
        city_label="Timișoara, Cluj-Napoca",
    )
    assert email1 is not None
    assert email1[0] == "[Timișoara, Cluj-Napoca] 1 best, 1 other jobs: Bosch, Nokia"

    email2 = format_email(
        {"best": [job("1", "Nokia")], "other": []}, [], city_label="Romania"
    )
    assert email2 is not None
    assert email2[0] == "[Romania] 1 best job: Nokia"

    email3 = format_email({}, ["Haufe check broke: boom"], city_label="Cluj-Napoca")
    assert email3 is not None
    assert email3[0] == "[Cluj-Napoca] job alert: Haufe check broke: boom"

    assert format_email({}, [], city_label="Timișoara") is None
