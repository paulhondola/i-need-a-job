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


def collect_results(results: dict) -> tuple[list[dict], list[str]]:
    """Collect deduplicated jobs and error notes from fetch results."""
    jobs, notes = [], []
    for source, result in results.items():
        if isinstance(result, Exception):
            notes.append(
                f"{source} check broke: {str(result) or type(result).__name__}"
            )
            continue
        deduped = {str(j["id"]): {**j, "id": str(j["id"])} for j in result}
        print(f"{source}: {len(deduped)} jobs")
        jobs.extend(deduped.values())
    return jobs, notes
