import json

from job_radar.cities import DEFAULT_CITY_FILTER, CityFilter
from job_radar.client import HTTP


def fetch_porsche(city_filter: CityFilter = DEFAULT_CITY_FILTER) -> list[dict]:
    query = {
        "LanguageCode": "EN",
        "SearchParameters": {
            "FirstItem": 1,
            "CountItem": 500,
            "MatchedObjectDescriptor": [
                "ID",
                "PositionTitle",
                "PositionURI",
                "PositionLocation.CityName",
                "ParentOrganizationName",
            ],
        },
        # 176 = Romania, channel 12 = public board (from jobs.porsche.com search URL)
        "SearchCriteria": [
            {"CriterionName": "PositionLocation.Country", "CriterionValue": ["176"]},
            {"CriterionName": "PublicationChannel.Code", "CriterionValue": ["12"]},
        ],
    }
    data = (
        HTTP.get(
            "https://porsche-beesite-production-gjb.app.beesite.de/search/",
            params={"data": json.dumps(query)},
        )
        .raise_for_status()
        .json()
    )
    jobs = []
    for item in data["SearchResult"]["SearchResultItems"]:
        d = item["MatchedObjectDescriptor"]
        cities = list(
            dict.fromkeys(
                name
                for loc in (d.get("PositionLocation") or [])
                if isinstance(loc, dict)
                and (name := (loc.get("CityName") or "").strip())
            )
        )
        if city_filter.is_all or any(city_filter.matches(c) for c in cities):
            jobs.append(
                {
                    "id": str(d["ID"]),
                    "title": d["PositionTitle"],
                    "company": d["ParentOrganizationName"],
                    "location": "; ".join(cities),
                    "url": d["PositionURI"],
                }
            )
    return jobs
