"""The companies to watch. One entry per company; the key is its name in seen.json and in emails.

Adding a company that uses a known hiring system is one line here. Its first run is silent.
"""
from collections.abc import Callable
from functools import partial

from job_radar.sources import beesite, greenhouse, oracle, workday

FETCHERS: dict[str, Callable[[], list[dict]]] = {
    "Porsche": beesite.fetch_porsche,
    "OPSWAT": partial(greenhouse.fetch, board="opswat", company="OPSWAT"),
    "Nokia": partial(oracle.fetch, api_host="fa-evmr-saasfaprod1.fa.ocs.oraclecloud.com", site="CX_1",
                     job_url_prefix="https://jobs.nokia.com/en/sites/CX_1/job/", company="Nokia"),
    "Intel": partial(workday.fetch, host="intel.wd1.myworkdayjobs.com", tenant="intel", site="External", company="Intel"),
}
