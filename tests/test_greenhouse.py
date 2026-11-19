import httpx

from job_radar.cities import parse_city_filter
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


def test_greenhouse_filters_by_custom_city_filter(monkeypatch):
    payload = {
        "jobs": [
            {
                "id": 103,
                "title": "Timisoara Engineer",
                "location": {"name": "Athens, Greece; Timișoara, Romania"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/103",
            },
            {
                "id": 104,
                "title": "Bucharest Engineer",
                "location": {"name": "Bucharest, Romania"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/104",
            },
            {
                "id": 105,
                "title": "Athens Engineer",
                "location": {"name": "Athens, Greece"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/105",
            },
        ]
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    )
    monkeypatch.setattr(greenhouse, "HTTP", client)

    buc = greenhouse.fetch(
        board="acme", company="Acme", city_filter=parse_city_filter(["bucharest"])
    )
    assert [j["id"] for j in buc] == ["104"]

    both = greenhouse.fetch(
        board="acme",
        company="Acme",
        city_filter=parse_city_filter(["timisoara,bucharest"]),
    )
    assert [j["id"] for j in both] == ["103", "104"]
