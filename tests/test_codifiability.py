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


from lexaugraph.codifiability import _parse_verification_status  # noqa: E402


def test_parse_verification_status_defaults_to_not_yet_checked():
    assert _parse_verification_status("/akn/au/act/1988/119", {}) == "not_yet_checked"


def test_parse_verification_status_returns_recorded_value():
    data = {"/akn/au/act/1988/119": "spot_checked"}
    assert _parse_verification_status("/akn/au/act/1988/119", data) == "spot_checked"


def test_parse_verification_status_unrecorded_act_defaults_even_with_other_data_present():
    data = {"/akn/au/act/1988/119": "spot_checked"}
    assert _parse_verification_status("/akn/au/act/1999/9", data) == "not_yet_checked"


from lexaugraph.codifiability import (  # noqa: E402
    build_signal1_prompt,
    parse_signal_response,
)


def test_build_signal1_prompt_includes_section_text():
    prompt = build_signal1_prompt("A person who is 18 years or older may apply.")
    assert "A person who is 18 years or older may apply." in prompt


def test_parse_signal_response_strips_markdown_fences_and_parses_json():
    raw = '```json\n{"tag": "high", "reasoning": "clear numeric threshold"}\n```'
    result = parse_signal_response(raw)
    assert result == {"tag": "high", "reasoning": "clear numeric threshold"}


def test_parse_signal_response_parses_plain_json_without_fences():
    raw = '{"tag": "low", "reasoning": "hinges on reasonableness"}'
    result = parse_signal_response(raw)
    assert result == {"tag": "low", "reasoning": "hinges on reasonableness"}


def test_parse_signal_response_returns_none_for_invalid_json():
    assert parse_signal_response("not json at all") is None


def test_parse_signal_response_returns_none_for_invalid_tag_value():
    raw = '{"tag": "very-high", "reasoning": "..."}'
    assert parse_signal_response(raw) is None


def test_parse_signal_response_returns_none_when_reasoning_missing():
    raw = '{"tag": "high"}'
    assert parse_signal_response(raw) is None


from lexaugraph.codifiability import build_signal2_prompt  # noqa: E402


def test_build_signal2_prompt_includes_section_text():
    prompt = build_signal2_prompt("Reasonable steps must be taken in the circumstances.")
    assert "Reasonable steps must be taken in the circumstances." in prompt
