from __future__ import annotations
import hashlib
import json
import re
import time
from typing import Literal


# ALRC's Obligations_word_count list, per their Explanatory Note
# (alrc.gov.au/wp-content/uploads/2022/12/Explanatory-Note-Complexity-and-
# linguistic-data.pdf, fetched 2026-08-05) -- 7 words.
_PRESCRIPTIVE_DENSITY_WORDS_7 = [
    "must", "shall", "may not", "prohibited", "required", "may only", "cannot be",
]
_PRESCRIPTIVE_DENSITY_PATTERN_7 = re.compile(
    r"\b(?:" + "|".join(_PRESCRIPTIVE_DENSITY_WORDS_7) + r")\b", re.IGNORECASE
)

# RegData Australia's exact restriction-word list (McLaughlin, Potts & Sherouse,
# "RegData: Australia," Mercatus Working Paper, June 2019, p.15) -- a strict
# subset of the 7-word list above, reported separately for direct comparison
# against RDAU1.0's own published dataset.
_PRESCRIPTIVE_DENSITY_WORDS_5 = ["shall", "must", "may not", "prohibited", "required"]
_PRESCRIPTIVE_DENSITY_PATTERN_5 = re.compile(
    r"\b(?:" + "|".join(_PRESCRIPTIVE_DENSITY_WORDS_5) + r")\b", re.IGNORECASE
)


def _prescriptive_density_tag(count: int) -> Literal["low", "medium", "high"]:
    # First-pass calibration -- not independently validated against real corpus
    # distribution. See scripts/codifiability_validation_pilot.py for real-corpus
    # cross-correlation against ALRC/RegData Australia.
    if count >= 5:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def _parse_verification_status(
    act_frbr_uri: str, verification_data: dict[str, str]
) -> Literal["spot_checked", "not_yet_checked"]:
    return verification_data.get(act_frbr_uri, "not_yet_checked")


_SIGNAL1_SYSTEM_PROMPT = (
    "You assess whether a provision of Australian Commonwealth legislation can be "
    "expressed as a deterministic, machine-codifiable rule (Rules-as-Code readiness). "
    "Classify the provision's codifiability as exactly one of: high, medium, low.\n\n"
    "- high: the provision reduces to a deterministic rule over objectively-verifiable "
    "facts (dates, numeric thresholds, enumerated categories) with no judgment call.\n"
    "- medium: mostly deterministic but hinges on one bounded, well-defined "
    "discretionary element (e.g. a Minister's approval of a specific enumerated list "
    "of grounds).\n"
    "- low: hinges on an open-ended standard (reasonableness, good faith, "
    "proportionality, \"in the circumstances\") that cannot be reduced to a fixed rule set.\n\n"
    "Return ONLY valid JSON -- no markdown fences, no commentary. Schema: "
    '{"tag": "high"|"medium"|"low", "reasoning": "one sentence"}'
)


def build_signal1_prompt(section_text: str) -> str:
    return f"## Provision text\n{section_text}\n\n## Task\nClassify this provision's codifiability."


def parse_signal_response(raw_text: str) -> dict | None:
    """Strip markdown fences, parse JSON, validate {tag, reasoning} shape.

    Shared by signal 1 (codifiability tag) and signal 2 (vagueness tag) -- both
    prompts use the identical {tag, reasoning} output schema. Returns None for any
    malformed response (bad JSON, wrong shape, invalid tag value) rather than
    raising, so one bad response in a large batch doesn't crash the whole run --
    the caller treats None the same as "not yet scored".
    """
    text = raw_text.strip()
    text = re.sub(r"^```json\n?", "", text)
    text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    tag = data.get("tag")
    reasoning = data.get("reasoning")
    if tag not in ("high", "medium", "low") or not isinstance(reasoning, str):
        return None
    return {"tag": tag, "reasoning": reasoning}


_SIGNAL2_SYSTEM_PROMPT = (
    "You assess how open-textured (vague) a provision of Australian Commonwealth "
    "legislation is -- whether its key terms admit of degree, require contextual "
    "judgment, or lack a fixed extension, versus being precisely and objectively "
    "bounded. Classify the provision's vagueness as exactly one of: high, medium, low.\n\n"
    "- high: the provision's operative test relies on open-ended, context-dependent "
    "standards throughout (e.g. \"reasonable in the circumstances\", \"in good faith\").\n"
    "- medium: the provision is mostly precise but contains one open-textured element.\n"
    "- low: the provision's operative test uses only precisely bounded terms (fixed "
    "thresholds, enumerated categories, defined terms).\n\n"
    "Return ONLY valid JSON -- no markdown fences, no commentary. Schema: "
    '{"tag": "high"|"medium"|"low", "reasoning": "one sentence"}'
)


def build_signal2_prompt(section_text: str) -> str:
    return f"## Provision text\n{section_text}\n\n## Task\nClassify this provision's open-texture/vagueness."


_BATCH_MODEL = "claude-haiku-4-5-20251001"
_BATCH_MAX_TOKENS = 300
_BATCH_POLL_INTERVAL_SECONDS = 30


def _custom_id(signal: str, node_id: str) -> str:
    """Batch API custom_id is capped at 64 characters by Anthropic -- real Act
    FRBR URIs + section eids can exceed that (e.g. long Part/Division/section eid
    chains). Hash to a fixed-length digest instead of using node_id directly; the
    caller keeps its own custom_id -> node_id map (see build_batch_requests) to
    attribute results back correctly. This mirrors a real bug hit and fixed
    elsewhere in this project (Chronicle's submit_code_summaries originally used
    full file paths as custom_id and every submission was rejected outright)."""
    digest = hashlib.sha256(f"{signal}:{node_id}".encode()).hexdigest()[:16]
    return f"{signal}_{digest}"


def build_batch_requests(
    signal: str,
    items: list[tuple[str, str]],  # (node_id, section_text)
    system_prompt: str,
    prompt_builder,
) -> tuple[list[dict], dict[str, str]]:
    """Returns (batch requests ready for client.messages.batches.create, a
    custom_id -> node_id map required by fetch_batch_results to attribute each
    response back to the right provision)."""
    id_map: dict[str, str] = {}
    requests: list[dict] = []
    for node_id, section_text in items:
        custom_id = _custom_id(signal, node_id)
        id_map[custom_id] = node_id
        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": _BATCH_MODEL,
                "max_tokens": _BATCH_MAX_TOKENS,
                "system": system_prompt,
                "messages": [{"role": "user", "content": prompt_builder(section_text)}],
            },
        })
    return requests, id_map


def submit_batch(requests: list[dict], client) -> str:
    batch = client.messages.batches.create(requests=requests)
    return batch.id


def wait_for_batch(batch_id: str, client, poll_interval: int = _BATCH_POLL_INTERVAL_SECONDS) -> None:
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            return
        time.sleep(poll_interval)


def fetch_batch_results(batch_id: str, client, id_map: dict[str, str]) -> dict[str, dict | None]:
    """Returns {node_id: parsed_response_or_None} -- None for any request that
    errored, expired, was canceled, or returned malformed/unparseable JSON."""
    results: dict[str, dict | None] = {}
    for entry in client.messages.batches.results(batch_id):
        node_id = id_map.get(entry.custom_id)
        if node_id is None:
            continue  # defensive only -- every custom_id we submit is in id_map
        if entry.result.type != "succeeded":
            results[node_id] = None
            continue
        text_blocks = [b.text for b in entry.result.message.content if getattr(b, "type", None) == "text"]
        if not text_blocks:
            results[node_id] = None
            continue
        results[node_id] = parse_signal_response(text_blocks[0])
    return results
