from __future__ import annotations
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
