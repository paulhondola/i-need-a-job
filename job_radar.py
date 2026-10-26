"""Check employers' careers APIs for new Timișoara jobs and email the new ones."""
import copy
import unicodedata


def matches_timisoara(location: str) -> bool:
    # NFKD splits both ș (comma) and ş (cedilla) into "s" + a combining mark.
    plain = "".join(c for c in unicodedata.normalize("NFKD", location) if not unicodedata.combining(c))
    plain = plain.casefold().strip()
    # ponytail: country-only "Romania" counts; these employers' Romanian office is in Timișoara
    return "timisoara" in plain or plain == "romania"


def update_state(state: dict, results: dict) -> tuple[dict, dict, list[str]]:
    """Diff fetch results against state. Returns (new_state, new_jobs_by_source, notes)."""
    state = copy.deepcopy(state)
    seen, broken = state["seen"], state["broken"]
    new_jobs, notes = {}, []
    for source, result in results.items():
        if isinstance(result, Exception):
            if source not in broken:
                broken.append(source)
                notes.append(f"{source} check broke: {result}")
            continue
        if source in broken:
            broken.remove(source)
            notes.append(f"{source} check recovered")
        jobs = {str(j["id"]): {**j, "id": str(j["id"])} for j in result}
        if source not in seen:
            seen[source] = sorted(jobs)
            continue
        fresh = [j for id, j in jobs.items() if id not in seen[source]]
        if fresh:
            new_jobs[source] = fresh
            seen[source] = sorted(set(seen[source]) | {j["id"] for j in fresh})
    state["broken"] = sorted(broken)
    return state, new_jobs, notes
