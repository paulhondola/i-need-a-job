import httpx

HTTP = httpx.Client(
    timeout=30,
    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"},
    follow_redirects=True,
)
