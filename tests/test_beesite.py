import json

import httpx

from job_radar.cities import parse_city_filter
from job_radar.sources import beesite


def _item(id: int, title: str, city: str | None) -> dict:
    locs = [{"CityName": city}] if city is not None else []
    return {
        "MatchedObjectDescriptor": {
            "ID": id,
            "PositionTitle": title,
            "PositionURI": f"https://jobs.porsche.com/{id}",
            "PositionLocation": locs,
            "ParentOrganizationName": "Porsche Engineering Romania",
        }
    }


def test_beesite_queries_romania_only_strips_city_and_filters(monkeypatch):
    seen_criteria = []
    payload = {
        "SearchResult": {
            "SearchResultItems": [
                _item(1, "Python Dev", "Timisoara"),
                _item(2, "Cloud Dev", "Bucharest "),
                _item(3, "Embedded Dev", "Cluj"),
                _item(4, "Plant IT", "Jucu"),
                _item(5, "Missing Loc", None),
            ]
        }
    }

    def handler(req: httpx.Request) -> httpx.Response:
        query = json.loads(req.url.params["data"])
        seen_criteria.append(query["SearchCriteria"])
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(beesite, "HTTP", client)

    tm = beesite.fetch_porsche()
    assert [j["id"] for j in tm] == ["1"]
    assert all(c["CriterionName"] != "PositionLocation.City" for c in seen_criteria[0])
    assert {
        "CriterionName": "PositionLocation.Country",
        "CriterionValue": ["176"],
    } in seen_criteria[0]

    buc_cluj = beesite.fetch_porsche(city_filter=parse_city_filter(["bucharest,cluj"]))
    assert [(j["id"], j["location"]) for j in buc_cluj] == [
        ("2", "Bucharest"),
        ("3", "Cluj"),
    ]

    all_ro = beesite.fetch_porsche(city_filter=parse_city_filter(["all"]))
    assert [j["id"] for j in all_ro] == ["1", "2", "3", "4", "5"]
