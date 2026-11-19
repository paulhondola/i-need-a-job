import re

import httpx

from job_radar.cities import parse_city_filter
from job_radar.sources import oracle


def test_oracle_pagination_secondary_locations_and_null_primary_location(monkeypatch):
    pages = {
        0: {
            "items": [
                {
                    "TotalJobsCount": 4,
                    "requisitionList": [
                        {
                            "Id": "10",
                            "Title": "Null Primary Location Role",
                            "PrimaryLocation": None,
                            "secondaryLocations": [{"Name": None}],
                        },
                        {
                            "Id": "11",
                            "Title": "Secondary Timisoara Engineer",
                            "PrimaryLocation": "Bucharest, Romania",
                            "secondaryLocations": [
                                {"Name": None},
                                {"Name": "Timișoara, Romania"},
                            ],
                        },
                    ],
                }
            ]
        },
        2: {
            "items": [
                {
                    "TotalJobsCount": 4,
                    "requisitionList": [
                        {
                            "Id": "12",
                            "Title": "Primary Timisoara Engineer",
                            "PrimaryLocation": "Timisoara, Romania",
                            "secondaryLocations": [],
                        },
                        {
                            "Id": "13",
                            "Title": "Cluj Engineer",
                            "PrimaryLocation": "Cluj-Napoca, Romania",
                            "secondaryLocations": [],
                        },
                    ],
                }
            ]
        },
    }
    seen_offsets: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        finder = req.url.params["finder"]
        match = re.search(r"offset=(\d+)", finder)
        assert match is not None
        offset = int(match.group(1))
        seen_offsets.append(offset)
        return httpx.Response(200, json=pages[offset])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(oracle, "HTTP", client)

    jobs = oracle.fetch(
        api_host="example.fa.ocs.oraclecloud.com",
        site="CX_1",
        job_url_prefix="https://careers.example.com/job/",
        company="ExampleCo",
    )

    assert seen_offsets == [0, 2]
    assert jobs == [
        {
            "id": "11",
            "title": "Secondary Timisoara Engineer",
            "company": "ExampleCo",
            "location": "Bucharest, Romania; Timișoara, Romania",
            "url": "https://careers.example.com/job/11",
        },
        {
            "id": "12",
            "title": "Primary Timisoara Engineer",
            "company": "ExampleCo",
            "location": "Timisoara, Romania",
            "url": "https://careers.example.com/job/12",
        },
    ]


def test_oracle_filters_by_custom_city_filter(monkeypatch):
    page = {
        "items": [
            {
                "TotalJobsCount": 4,
                "requisitionList": [
                    {
                        "Id": "10",
                        "Title": "Null Primary Location Role",
                        "PrimaryLocation": None,
                        "secondaryLocations": [{"Name": None}],
                    },
                    {
                        "Id": "11",
                        "Title": "Secondary Timisoara Engineer",
                        "PrimaryLocation": "Bucharest, Romania",
                        "secondaryLocations": [{"Name": "Timișoara, Romania"}],
                    },
                    {
                        "Id": "12",
                        "Title": "Primary Timisoara Engineer",
                        "PrimaryLocation": "Timisoara, Romania",
                        "secondaryLocations": [],
                    },
                    {
                        "Id": "13",
                        "Title": "Cluj Engineer",
                        "PrimaryLocation": "Cluj-Napoca, Romania",
                        "secondaryLocations": [],
                    },
                ],
            }
        ]
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=page))
    )
    monkeypatch.setattr(oracle, "HTTP", client)

    cluj = oracle.fetch(
        api_host="example.fa.ocs.oraclecloud.com",
        site="CX_1",
        job_url_prefix="https://careers.example.com/job/",
        company="ExampleCo",
        city_filter=parse_city_filter(["cluj"]),
    )
    assert [j["id"] for j in cluj] == ["13"]

    all_ro = oracle.fetch(
        api_host="example.fa.ocs.oraclecloud.com",
        site="CX_1",
        job_url_prefix="https://careers.example.com/job/",
        company="ExampleCo",
        city_filter=parse_city_filter(["all"]),
    )
    assert [j["id"] for j in all_ro] == ["11", "12", "13"]
