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
