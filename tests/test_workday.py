import json

import httpx

from job_radar.cities import parse_city_filter
from job_radar.sources import workday


def posting(i: int) -> dict:
    return {
        "title": f"Engineer {i}",
        "externalPath": f"/job/Timisoara/Engineer_JR{i}",
        "locationsText": "Romania, Timisoara",
    }


def test_workday_facet_discovery_and_pagination_when_subsequent_totals_are_zero(
    monkeypatch,
):
    facets_response = {
        "facets": [
            {
                "facetParameter": "locationMainGroup",
                "values": [
                    {
                        "facetParameter": "locations",
                        "values": [
                            {"id": "loc-tm", "descriptor": "Romania, Timisoara"},
                            {"id": "loc-b", "descriptor": "Romania, Bucharest"},
                        ],
                    }
                ],
            }
        ]
    }
    pages = {
        0: {
            "total": 45,
            "jobPostings": [
                {"bulletFields": ["R00298206", "Location Negotiable"]},
                *[posting(i) for i in range(19)],
            ],
        },
        20: {"total": 0, "jobPostings": [posting(i) for i in range(19, 39)]},
        40: {"total": 0, "jobPostings": [posting(i) for i in range(39, 44)]},
    }

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if body["appliedFacets"] == {}:
            return httpx.Response(200, json=facets_response)
        assert body["appliedFacets"] == {"locations": ["loc-tm"]}
        return httpx.Response(200, json=pages[body["offset"]])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(workday, "HTTP", client)

    jobs = workday.fetch(
        host="intel.wd1.myworkdayjobs.com",
        tenant="intel",
        site="External",
        company="Intel",
    )
    assert len(jobs) == 44
    assert [j["id"] for j in jobs] == [f"JR{i}" for i in range(44)]
    assert jobs[0] == {
        "id": "JR0",
        "title": "Engineer 0",
        "company": "Intel",
        "location": "Romania, Timisoara",
        "url": "https://intel.wd1.myworkdayjobs.com/External/job/Timisoara/Engineer_JR0",
    }


def test_workday_multi_city_passes_all_matched_facet_ids(monkeypatch):
    facets_response = {
        "facets": [
            {
                "facetParameter": "locationMainGroup",
                "values": [
                    {
                        "facetParameter": "locations",
                        "values": [
                            {"id": "loc-tm", "descriptor": "Romania, Timisoara"},
                            {"id": "loc-b", "descriptor": "Romania, Bucharest"},
                            {"id": "loc-de", "descriptor": "Germany, Munich"},
                        ],
                    }
                ],
            }
        ]
    }
    seen_facets = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if body["appliedFacets"] == {}:
            return httpx.Response(200, json=facets_response)
        seen_facets.append(body["appliedFacets"])
        return httpx.Response(200, json={"total": 1, "jobPostings": [posting(0)]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(workday, "HTTP", client)

    jobs = workday.fetch(
        host="intel.wd1.myworkdayjobs.com",
        tenant="intel",
        site="External",
        company="Intel",
        city_filter=parse_city_filter(["timisoara,bucharest"]),
    )
    assert seen_facets == [{"locations": ["loc-tm", "loc-b"]}]
    assert len(jobs) == 1
