"""The companies to watch. One entry per company; the key is its name in seen.json and in emails.

Adding a company that uses a known hiring system is one line here. Its first run is silent.
"""
from collections.abc import Callable
from functools import partial

from job_radar.sources import (beesite, greenhouse, lever, oracle, personio, rinf, smartrecruiters, successfactors,
                               teamtailor, telekom, workday)

FETCHERS: dict[str, Callable[[], list[dict]]] = {
    "Porsche": beesite.fetch_porsche,
    "OPSWAT": partial(greenhouse.fetch, board="opswat", company="OPSWAT"),
    "Nokia": partial(oracle.fetch, api_host="fa-evmr-saasfaprod1.fa.ocs.oraclecloud.com", site="CX_1",
                     job_url_prefix="https://jobs.nokia.com/en/sites/CX_1/job/", company="Nokia"),
    "Intel": partial(workday.fetch, host="intel.wd1.myworkdayjobs.com", tenant="intel", site="External", company="Intel"),
    "Endava": partial(smartrecruiters.fetch, slug="endava", company="Endava"),
    "Aumovio": partial(smartrecruiters.fetch, slug="aumovio", company="Aumovio"),
    "Manage Now": partial(personio.fetch, slug="manage-now", company="Manage Now",
                          job_url="https://jobs.manage-now.de/job.php?id={id}"),
    # d.velop links jobs by title slug, not id: point at the listing.
    "d.velop": partial(personio.fetch, slug="d-velop", company="d.velop", job_url="https://karriere.d-velop.de/stellenanzeigen/"),
    "Bosch": partial(smartrecruiters.fetch, slug="BoschGroup", company="Bosch"),
    "Accenture": partial(workday.fetch, host="accenture.wd103.myworkdayjobs.com", tenant="accenture", site="AccentureCareers", company="Accenture"),
    "TE Connectivity": partial(successfactors.fetch, host="careers.te.com", company="TE Connectivity"),
    "Visma": partial(teamtailor.fetch, slug="vismacc", company="Visma"),
    "Atos": partial(successfactors.fetch, host="jobs.atos.net", company="Atos"),
    "EY": partial(successfactors.fetch, host="careers.ey.com", company="EY"),
    "Schaeffler": partial(successfactors.fetch, host="jobs.schaeffler.com", company="Schaeffler"),
    "DRÄXLMAIER": partial(successfactors.fetch, host="d-career.org", company="DRÄXLMAIER"),
    "NTT DATA": partial(successfactors.fetch, host="careers.nttdata.ro", company="NTT DATA"),
    # SAP is moving to SmartRecruiters; until done, some roles stay on the old SuccessFactors site.
    "SAP": partial(smartrecruiters.fetch, slug="SAPITBusinessSysteme", company="SAP"),
    "SAP (old site)": partial(successfactors.fetch, host="careers.sap.com", company="SAP"),
    "Deutsche Telekom": telekom.fetch,
    "Everseen": partial(lever.fetch, slug="everseen", company="Everseen", api_host="api.eu.lever.co"),
    "rinf.tech": rinf.fetch,
    # No Timișoara roles on its board today, but its R&D centre is there.
    "Huf": partial(successfactors.fetch, host="jobs.huf-group.com", company="Huf"),
}
