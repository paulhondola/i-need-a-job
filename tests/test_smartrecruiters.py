import httpx

from job_radar.sources import smartrecruiters


def posting(id, city, remote=False):
    return {"id": id, "name": f"Job {id}", "company": {"identifier": "Nagarro1"},
            "location": {"city": city, "country": "ro", "remote": remote, "fullLocation": f"{city}, , Romania"}}


def test_keeps_timisoara_and_remote_romania_drops_other_cities(monkeypatch):
    page = {"totalFound": 3, "content": [posting("1", "Timișoara"), posting("2", "Remote", remote=True),
                                         posting("3", "Bucharest")]}
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=page)))
    monkeypatch.setattr(smartrecruiters, "HTTP", client)
    assert [j["id"] for j in smartrecruiters.fetch(slug="Nagarro1", company="Nagarro")] == ["1", "2"]
