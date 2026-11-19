import httpx
import pytest

from job_radar.cities import parse_city_filter
from job_radar.sources import rinf

SIDEBAR_HTML = (
    '<input type="checkbox" name="city-bucharest"/>'
    '<span class="whitespace-nowrap text-sm">Bucharest<span>(23)</span></span>'
    '<input type="checkbox" name="city-timisoara"/>'
    '<span class="whitespace-nowrap text-sm">Timisoara<span>(2)</span></span>'
    '<input type="checkbox" name="city-cluj-napoca"/>'
    '<span class="whitespace-nowrap text-sm">Cluj-Napoca<span>(1)</span></span>'
    '<input type="checkbox" name="city-detroit"/>'
    '<span class="whitespace-nowrap text-sm">Detroit<span>(4)</span></span>'
)


def test_rinf_unescapes_titles_and_stops_when_page_repeats(monkeypatch):
    cards_html = (
        '<a href="/101"><p class="job-title">C &amp; C++ Developer</p></a>'
        '<a href="/102"><p>Python Engineer</p></a>'
    )
    requested_pages = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "city" not in req.url.params:
            return httpx.Response(200, text=SIDEBAR_HTML)
        assert req.url.params["city"] == "Timisoara"
        requested_pages.append(req.url.params["page"])
        return httpx.Response(200, text=cards_html)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(rinf, "HTTP", client)

    jobs = rinf.fetch()
    assert requested_pages == ["1", "2"]
    assert jobs == [
        {
            "id": "101",
            "title": "C & C++ Developer",
            "company": "rinf.tech",
            "location": "Timisoara",
            "url": "https://jobs.rinf.tech/101",
        },
        {
            "id": "102",
            "title": "Python Engineer",
            "company": "rinf.tech",
            "location": "Timisoara",
            "url": "https://jobs.rinf.tech/102",
        },
    ]


def test_rinf_multi_city_alias_matching_and_dedup_merges_locations(monkeypatch):
    by_city = {
        "Timisoara": (
            '<a href="/101"><p>Shared Engineer</p></a>'
            '<a href="/102"><p>Timisoara Only</p></a>'
        ),
        "Cluj-Napoca": (
            '<a href="/101"><p>Shared Engineer</p></a>'
            '<a href="/103"><p>Cluj Only</p></a>'
        ),
    }
    queried_cities = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "city" not in req.url.params:
            return httpx.Response(200, text=SIDEBAR_HTML)
        city = req.url.params["city"]
        queried_cities.append(city)
        return httpx.Response(200, text=by_city[city])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(rinf, "HTTP", client)

    jobs = rinf.fetch(city_filter=parse_city_filter(["timisoara,cluj"]))
    assert set(queried_cities) == {"Timisoara", "Cluj-Napoca"}
    assert [(j["id"], j["location"]) for j in jobs] == [
        ("101", "Timisoara; Cluj-Napoca"),
        ("102", "Timisoara"),
        ("103", "Cluj-Napoca"),
    ]


def test_rinf_unlisted_city_returns_empty_when_sidebar_present(monkeypatch):
    requests = []

    def handler(req: httpx.Request) -> httpx.Response:
        requests.append(dict(req.url.params))
        return httpx.Response(200, text=SIDEBAR_HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(rinf, "HTTP", client)

    assert rinf.fetch(city_filter=parse_city_filter(["arad"])) == []
    assert requests == [{}]


def test_rinf_all_uses_country_romania(monkeypatch):
    cards_html = '<a href="/201"><p>Romania Engineer</p></a>'
    seen_params = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_params.append(dict(req.url.params))
        return httpx.Response(200, text=cards_html)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(rinf, "HTTP", client)

    jobs = rinf.fetch(city_filter=parse_city_filter(["all"]))
    assert seen_params == [
        {"country": "Romania", "page": "1"},
        {"country": "Romania", "page": "2"},
    ]
    assert jobs == [
        {
            "id": "201",
            "title": "Romania Engineer",
            "company": "rinf.tech",
            "location": "Romania",
            "url": "https://jobs.rinf.tech/201",
        }
    ]


def test_rinf_raises_when_sidebar_has_no_city_checkboxes(monkeypatch):
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, text="<html><body>redesigned</body></html>")
        )
    )
    monkeypatch.setattr(rinf, "HTTP", client)

    with pytest.raises(ValueError, match="no city filters"):
        rinf.fetch()
