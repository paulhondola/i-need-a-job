import httpx

from job_radar.sources import successfactors

# Huf's real "no results" feed: the placeholder item has a raw "&" from the company name, so it isn't valid XML.
EMPTY_FEED = """<?xml version="1.0" encoding="UTF-8" ?><rss version='2.0'><channel><title>Huf</title>
<item><title>No jobs currently available - Check out our other opportunities.</title>
<description>Click above to see other opportunities available at Huf Hülsbeck & Fürst GmbH & Co. KG</description>
<link>https://jobs.huf-group.com</link><guid isPermaLink='false'>0</guid></item></channel></rss>"""


def test_no_jobs_placeholder_feed_is_empty_not_broken(monkeypatch):
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=EMPTY_FEED)))
    monkeypatch.setattr(successfactors, "HTTP", client)
    assert successfactors.fetch(host="jobs.huf-group.com", company="Huf") == []
