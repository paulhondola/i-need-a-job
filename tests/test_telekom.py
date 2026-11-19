import httpx

from job_radar.cities import parse_city_filter
from job_radar.sources import telekom


def _posting(req_id: str, city: str) -> dict:
    return {"requisition_id": req_id, "title": f"Role {req_id}", "city": city}


def test_telekom_queries_romania_and_filters_by_city_and_all(monkeypatch):
    seen_locations = []
    pages = {
        "1": {
            "data": [_posting("1", "Timișoara"), _posting("2", "Bucharest")],
            "pagination_info": {"number_of_pages": 2},
        },
        "2": {
            "data": [_posting("3", "Romania"), _posting("4", "Jucu")],
            "pagination_info": {"number_of_pages": 2},
        },
    }

    def handler(req: httpx.Request) -> httpx.Response:
        seen_locations.append(req.url.params["location"])
        return httpx.Response(200, json=pages[req.url.params["page"]])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(telekom, "HTTP", client)

    tm = telekom.fetch()
    assert set(seen_locations) == {"Romania"}
    assert [j["id"] for j in tm] == ["1", "3"]

    buc = telekom.fetch(city_filter=parse_city_filter(["bucuresti"]))
    assert [j["id"] for j in buc] == ["2", "3"]

    all_ro = telekom.fetch(city_filter=parse_city_filter(["all"]))
    assert [j["id"] for j in all_ro] == ["1", "2", "3", "4"]
