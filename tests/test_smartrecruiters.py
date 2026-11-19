import httpx

from job_radar.sources import smartrecruiters


def posting(id, city=None, remote=False):
    loc = {"country": "ro", "remote": remote}
    if city:
        loc.update(city=city, fullLocation=f"{city}, , Romania")
    return {
        "id": id,
        "name": f"Job {id}",
        "company": {"identifier": "Nagarro1"},
        "location": loc,
    }


def test_keeps_timisoara_and_remote_romania_drops_other_cities(monkeypatch):
    page = {
        "totalFound": 3,
        "content": [
            posting("1", "Timișoara"),
            posting("2", remote=True),
            posting("3", "Bucharest"),
        ],
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=page))
    )
    monkeypatch.setattr(smartrecruiters, "HTTP", client)
    jobs = smartrecruiters.fetch(slug="Nagarro1", company="Nagarro")
    assert [j["id"] for j in jobs] == ["1", "2"]
    assert jobs[1]["location"] == "Romania"
