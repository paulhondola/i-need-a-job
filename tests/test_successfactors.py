import httpx

from job_radar.sources import successfactors

# Huf's real "no results" feed: the placeholder item has a raw "&" from the company name, so it isn't valid XML.
EMPTY_FEED = """<?xml version="1.0" encoding="UTF-8" ?><rss version='2.0'><channel><title>Huf</title>
<item><title>No jobs currently available - Check out our other opportunities.</title>
<description>Click above to see other opportunities available at Huf Hülsbeck & Fürst GmbH & Co. KG</description>
<link>https://jobs.huf-group.com</link><guid isPermaLink='false'>0</guid></item></channel></rss>"""


def test_no_jobs_placeholder_feed_is_empty_not_broken(monkeypatch):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text=EMPTY_FEED))
    )
    monkeypatch.setattr(successfactors, "HTTP", client)
    assert successfactors.fetch(host="jobs.huf-group.com", company="Huf") == []


MULTI_ITEM_FEED = """<?xml version="1.0" encoding="UTF-8" ?><rss version='2.0'><channel><title>EY</title>
<item><title>Working Student (m/f/d) (TIMISOARA, TM, RO, 307160)</title>
<description>Join our Strategy & Transactions team in Timisoara.</description>
<link>https://careers.ey.com/ey/job/Timisoara-Working-Student/1407355633/?feedId=1</link></item>
<item><title>R&amp;amp;D Software Engineer (Timisoara (Hybrid), RO)</title>
<description>Build cloud services.</description>
<link>https://careers.ey.com/ey/job/Timisoara-SE/1407356333/</link></item>
<item><title>Consultant (Bucharest, Romania)</title>
<description>Consulting role in Bucharest.</description>
<link>https://careers.ey.com/ey/job/Bucharest-Consultant/1407478533/</link></item>
</channel></rss>"""


def test_fetch_parses_active_feed_and_filters_timisoara(monkeypatch):
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, text=MULTI_ITEM_FEED)
        )
    )
    monkeypatch.setattr(successfactors, "HTTP", client)
    assert successfactors.fetch(host="careers.ey.com", company="EY") == [
        {
            "id": "1407355633",
            "title": "Working Student (m/f/d)",
            "company": "EY",
            "location": "TIMISOARA, TM, RO, 307160",
            "url": "https://careers.ey.com/ey/job/Timisoara-Working-Student/1407355633/",
        },
        {
            "id": "1407356333",
            "title": "R&D Software Engineer",
            "company": "EY",
            "location": "Timisoara (Hybrid), RO",
            "url": "https://careers.ey.com/ey/job/Timisoara-SE/1407356333/",
        },
    ]
