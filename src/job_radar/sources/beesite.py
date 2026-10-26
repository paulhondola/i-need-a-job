import json

from job_radar.client import HTTP


def fetch_porsche() -> list[dict]:
    query = {
        "LanguageCode": "EN",
        "SearchParameters": {
            "FirstItem": 1,
            "CountItem": 500,
            "MatchedObjectDescriptor": ["ID", "PositionTitle", "PositionURI", "PositionLocation.CityName", "ParentOrganizationName"],
        },
        # 176 = Romania, 311 = Timișoara, channel 12 = public board (from jobs.porsche.com search URL)
        "SearchCriteria": [
            {"CriterionName": "PositionLocation.Country", "CriterionValue": ["176"]},
            {"CriterionName": "PositionLocation.City", "CriterionValue": ["311"]},
            {"CriterionName": "PublicationChannel.Code", "CriterionValue": ["12"]},
        ],
    }
    data = HTTP.get("https://porsche-beesite-production-gjb.app.beesite.de/search/", params={"data": json.dumps(query)}).raise_for_status().json()
    return [
        {
            "id": str(d["ID"]),
            "title": d["PositionTitle"],
            "company": d["ParentOrganizationName"],
            "location": d["PositionLocation"][0]["CityName"],
            "url": d["PositionURI"],
        }
        for d in (item["MatchedObjectDescriptor"] for item in data["SearchResult"]["SearchResultItems"])
    ]
