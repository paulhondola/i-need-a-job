import httpx

from job_radar.sources import rinf


def test_rinf_unescapes_titles_and_stops_when_page_repeats(monkeypatch):
    html = (
        '<a href="/101"><p class="job-title">C &amp; C++ Developer</p></a>'
        '<a href="/102"><p>Python Engineer</p></a>'
    )
    requested_pages = []

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["city"] == "Timisoara"
        requested_pages.append(req.url.params["page"])
        return httpx.Response(200, text=html)

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
