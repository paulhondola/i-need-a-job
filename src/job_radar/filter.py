import json
import os
import re
import sys
from pathlib import Path

from job_radar.client import HTTP

DEFAULT_PREFERENCES_PATH = Path(__file__).resolve().parents[2] / "preferences.md"
_CHUNK_SIZE = 200

_DROP_RE = re.compile(
    r"\b("
    r"senior|sr\.?|lead|team\s*lead|tech\s*lead|principal|staff|architect|manager|director|head\s+of|vp|vice\s+president|chief|expert"
    r"|hr|human\s+resources|recruiter|recruiting|talent\s+acquisition|payroll"
    r"|finance|financial|accountant|accounting|controlling|cost\s+controller|tax|audit|treasury"
    r"|procurement|purchasing|buyer|einkauf"
    r"|legal|counsel|paralegal"
    r"|sales|account\s+executive|marketing|copywriter"
    r"|logistics|supply\s+chain|(?<!data\s)warehouse|customs"
    r"|mechanical|electrical\s+design|wiring|harness|manufacturing|production\s+planner|plant|facility|receptionist|assistant\s+to"
    r"|german\s+speaker|with\s+german|german\s+language"
    r")\b",
    re.IGNORECASE,
)

_SYSTEM_SUFFIX = (
    "\n\nReturn ONLY a JSON object with two integer arrays: "
    '{"best": [<index>, ...], "other": [<index>, ...]}. '
    "Each index corresponds to a numbered job in the user prompt. "
    "Omit indices of jobs that should be dropped."
)


def regex_prefilter(jobs: list[dict]) -> list[dict]:
    """Drop jobs whose title matches excluded seniority, department, or language terms."""
    return [j for j in jobs if not _DROP_RE.search(j["title"])]


def llm_filter(jobs: list[dict], preferences: str) -> dict[str, list[dict]]:
    """Classify jobs into 'best' and 'other' tiers via an OpenAI-compatible LLM endpoint."""
    if not jobs:
        return {"best": [], "other": []}
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip(
        "/"
    )
    model = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}

    best: list[dict] = []
    other: list[dict] = []
    # Batch in chunks of 200 to stay comfortably under Groq's 12,000 TPM free-tier limit.
    for start in range(0, len(jobs), _CHUNK_SIZE):
        chunk = jobs[start : start + _CHUNK_SIZE]
        lines = "\n".join(
            f"{idx}: [{j['company']}] {j['title']} ({j['location']})"
            for idx, j in enumerate(chunk)
        )
        payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": preferences.strip() + _SYSTEM_SUFFIX},
                {"role": "user", "content": lines},
            ],
        }
        resp = HTTP.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict) or (
            "best" not in parsed and "other" not in parsed
        ):
            raise ValueError("LLM response JSON missing 'best'/'other' keys")

        seen_in_chunk: set[int] = set()
        for tier_key, target in (("best", best), ("other", other)):
            raw_indices = parsed.get(tier_key)
            if raw_indices is None:
                continue
            if not isinstance(raw_indices, list):
                raise TypeError(f"LLM response tier {tier_key!r} is not a list")
            for idx in raw_indices:
                # bool is a subclass of int in Python; exclude it explicitly.
                if (
                    isinstance(idx, int)
                    and not isinstance(idx, bool)
                    and 0 <= idx < len(chunk)
                    and idx not in seen_in_chunk
                ):
                    seen_in_chunk.add(idx)
                    target.append(chunk[idx])
    return {"best": best, "other": other}


def filter_jobs(
    jobs_by_source: dict[str, list[dict]],
    preferences_path: Path = DEFAULT_PREFERENCES_PATH,
) -> tuple[dict[str, list[dict]], list[str]]:
    """Apply regex prefiltering and LLM tiering, falling back to 'other' on LLM failure."""
    all_jobs = [j for jobs in jobs_by_source.values() for j in jobs]
    surviving = regex_prefilter(all_jobs)
    notes: list[str] = []
    if not surviving:
        tiered = {"best": [], "other": []}
    else:
        try:
            preferences = preferences_path.read_text(encoding="utf-8")
            tiered = llm_filter(surviving, preferences)
        except Exception as e:  # noqa: BLE001
            print(f"llm filter: {e!r}", file=sys.stderr)
            notes.append(f"llm filter broke: {e}")
            tiered = {"best": [], "other": surviving}
    print(
        f"filter: {len(all_jobs)} total -> {len(surviving)} after regex -> "
        f"{len(tiered['best'])} best, {len(tiered['other'])} other"
    )
    return tiered, notes
