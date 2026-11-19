import httpx

from job_radar.sources import greenhouse


def test_greenhouse_handles_null_location_and_multi_location_timisoara(monkeypatch):
    payload = {
        "jobs": [
            {
                "id": 101,
                "title": "Null Location Name Role",
                "location": {"name": None},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
            },
            {
                "id": 102,
                "title": "Null Location Object Role",
                "location": None,
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/102",
            },
            {
                "id": 103,
                "title": "Senior Backend Engineer",
                "location": {"name": "Athens, Greece; Timișoara, Romania"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/103",
            },
            {
                "id": 104,
                "title": "Bucharest Only Engineer",
                "location": {"name": "Bucharest, Romania"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/104",
            },
        ]
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    )
    monkeypatch.setattr(greenhouse, "HTTP", client)

    jobs = greenhouse.fetch(board="acme", company="Acme")

    assert jobs == [
        {
            "id": "103",
            "title": "Senior Backend Engineer",
            "company": "Acme",
            "location": "Athens, Greece; Timișoara, Romania",
            "url": "https://boards.greenhouse.io/acme/jobs/103",
        }
    ]
