from __future__ import annotations

import json
from types import SimpleNamespace

from lexaugraph.llm_extract import (
    build_extraction_prompt,
    extract_definitions_from_section,
)

SECTION_TEXT = (
    "income support payment means a payment of: (a) a social security pension; or "
    "(b) a social security benefit; or (c) a service pension. "
    "other term means something else entirely different."
)


def _fake_client(response_text: str):
    """Build a fake anthropic.Anthropic-shaped client whose messages.create() returns
    a canned response object matching the real SDK's response.content[0].text shape."""
    response = SimpleNamespace(content=[SimpleNamespace(text=response_text)])
    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: response)
    )
    return client


def test_build_extraction_prompt_includes_section_text_and_terms():
    prompt = build_extraction_prompt(SECTION_TEXT, ["income support payment", "other term"])
    assert SECTION_TEXT in prompt
    assert "income support payment" in prompt
    assert "other term" in prompt


def test_valid_json_response_with_verbatim_substring_is_included():
    payload = json.dumps([
        {
            "term": "income support payment",
            "definition_text": (
                "income support payment means a payment of: (a) a social security pension; or "
                "(b) a social security benefit; or (c) a service pension."
            ),
        }
    ])
    client = _fake_client(payload)
    result = extract_definitions_from_section(SECTION_TEXT, ["income support payment"], client)
    assert len(result) == 1
    assert result[0]["term"] == "income support payment"
    assert result[0]["definition_text"] in SECTION_TEXT


def test_definition_not_substring_of_section_text_is_dropped():
    payload = json.dumps([
        {
            "term": "income support payment",
            "definition_text": "income support payment means literally anything the Secretary decides.",
        }
    ])
    client = _fake_client(payload)
    result = extract_definitions_from_section(SECTION_TEXT, ["income support payment"], client)
    assert result == []


def test_malformed_json_returns_empty_list_without_raising():
    client = _fake_client("this is not { valid json at all")
    result = extract_definitions_from_section(SECTION_TEXT, ["income support payment"], client)
    assert result == []


def test_markdown_fenced_json_is_stripped_and_parsed():
    payload = json.dumps([
        {
            "term": "other term",
            "definition_text": "other term means something else entirely different.",
        }
    ])
    fenced = f"```json\n{payload}\n```"
    client = _fake_client(fenced)
    result = extract_definitions_from_section(SECTION_TEXT, ["other term"], client)
    assert len(result) == 1
    assert result[0]["term"] == "other term"


def test_empty_candidate_terms_returns_empty_list_without_calling_client():
    calls = []
    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs))
    )
    result = extract_definitions_from_section(SECTION_TEXT, [], client)
    assert result == []
    assert calls == []
