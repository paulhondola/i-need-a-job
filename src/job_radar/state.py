import unicodedata


def matches_timisoara(location: str) -> bool:
    # NFKD splits both ș (comma) and ş (cedilla) into "s" + a combining mark.
    plain = "".join(
        c
        for c in unicodedata.normalize("NFKD", location)
        if not unicodedata.combining(c)
    )
    plain = plain.casefold().strip()
    # ponytail: country-only "Romania" counts; these employers' Romanian office is in Timișoara
    return "timisoara" in plain or plain == "romania"


def collect_results(results: dict) -> tuple[dict, list[str]]:
    """Collect deduplicated jobs by source and error notes from fetch results."""
    jobs_by_source, notes = {}, []
    for source, result in results.items():
        if isinstance(result, Exception):
            notes.append(f"{source} check broke: {result}")
            continue
        deduped = {str(j["id"]): {**j, "id": str(j["id"])} for j in result}
        if deduped:
            jobs_by_source[source] = list(deduped.values())
    return jobs_by_source, notes
