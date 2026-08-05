from __future__ import annotations
import networkx as nx
import pytest

from lexaugraph.codifiability import (
    _PRESCRIPTIVE_DENSITY_PATTERN_7,
    _PRESCRIPTIVE_DENSITY_PATTERN_5,
    _prescriptive_density_tag,
)
from lexaugraph.complexity import _count_matches


def test_prescriptive_density_7_word_pattern_matches_alrc_list():
    text = (
        "The Secretary must approve the application. A person shall not disclose "
        "the record. This action is prohibited without written consent. The "
        "applicant is required to provide evidence. The Minister may only act on "
        "enumerated grounds. This liability cannot be waived."
    )
    count = len(_PRESCRIPTIVE_DENSITY_PATTERN_7.findall(text))
    # must, shall, prohibited, required, may only, cannot be = 6
    # ("shall not" contains "shall" -- not "may not", so counted once for "shall")
    assert count == 6


def test_prescriptive_density_5_word_subset_excludes_may_only_and_cannot_be():
    text = "The Minister may only act on enumerated grounds. This liability cannot be waived."
    count = len(_PRESCRIPTIVE_DENSITY_PATTERN_5.findall(text))
    assert count == 0


def test_prescriptive_density_5_word_subset_matches_core_regdata_words():
    text = "The Secretary must approve. A person shall not disclose. This is prohibited. Evidence is required."
    count = len(_PRESCRIPTIVE_DENSITY_PATTERN_5.findall(text))
    assert count == 4


def test_prescriptive_density_tag_buckets_by_count():
    assert _prescriptive_density_tag(0) == "low"
    assert _prescriptive_density_tag(1) == "low"
    assert _prescriptive_density_tag(2) == "medium"
    assert _prescriptive_density_tag(4) == "medium"
    assert _prescriptive_density_tag(5) == "high"
    assert _prescriptive_density_tag(10) == "high"
