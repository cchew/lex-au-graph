from __future__ import annotations
import json
import re
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
