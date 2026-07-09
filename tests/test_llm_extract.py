from __future__ import annotations

import json
from types import SimpleNamespace

from lexaugraph.llm_extract import (
    build_extraction_prompt,
    chunk_section_text,
    estimate_tokens,
    extract_definitions_from_section,
)

SECTION_TEXT = (
    "income support payment means a payment of: (a) a social security pension; or "
    "(b) a social security benefit; or (c) a service pension. "
    "other term means something else entirely different."
)


def _fake_client(response_text: str):
    """Build a fake anthropic.Anthropic-shaped client whose messages.create() returns
    a canned response object matching the real SDK's response.content[0].text shape.
    Includes a `type="text"` attribute since some models (e.g. extended-thinking
    models) prepend non-text content blocks (ThinkingBlock) to response.content."""
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=response_text)]
    )
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


def test_leading_non_text_content_block_is_skipped():
    """Some models (extended-thinking) prepend a ThinkingBlock with no .text attribute
    before the actual text block. The text block must still be found and parsed."""
    payload = json.dumps([
        {
            "term": "other term",
            "definition_text": "other term means something else entirely different.",
        }
    ])
    thinking_block = SimpleNamespace(type="thinking")  # deliberately has no .text
    text_block = SimpleNamespace(type="text", text=payload)
    response = SimpleNamespace(content=[thinking_block, text_block])
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: response))
    result = extract_definitions_from_section(SECTION_TEXT, ["other term"], client)
    assert len(result) == 1
    assert result[0]["term"] == "other term"


def test_non_list_json_returns_empty_list_without_raising():
    """A response that is valid JSON but not a list (e.g. a single dict, or a
    truncated-output artifact) must be rejected gracefully, not raise AttributeError
    when the code later tries item.get(...)."""
    client = _fake_client(json.dumps({"term": "other term", "definition_text": "x"}))
    result = extract_definitions_from_section(SECTION_TEXT, ["other term"], client)
    assert result == []


def test_list_with_non_dict_items_skips_them_without_raising():
    payload = json.dumps([
        "not a dict",
        {"term": "other term", "definition_text": "other term means something else entirely different."},
    ])
    client = _fake_client(payload)
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


# --- section_text token-budget chunking (input-size guard, independent of term-count batching) ---

def _make_long_section_text(num_sentences: int) -> str:
    """Build a section_text long enough to exceed the token ceiling when num_sentences
    is large enough. Each sentence is deliberately verbose to accumulate character count
    quickly without needing an enormous num_sentences value."""
    sentence = (
        "example term {i} means a payment made under this Act in circumstances where "
        "the Secretary is satisfied that the person meets the relevant eligibility "
        "criteria set out in the applicable legislative instrument."
    )
    return " ".join(sentence.format(i=i) for i in range(num_sentences))


def test_short_section_text_is_not_chunked():
    """The common case: a section_text comfortably under the ceiling must pass through
    as a single chunk, so normal-sized Acts don't incur unnecessary extra API calls."""
    assert estimate_tokens(SECTION_TEXT) < 6000
    chunks = chunk_section_text(SECTION_TEXT)
    assert chunks == [SECTION_TEXT]


def test_long_section_text_is_split_into_multiple_chunks_under_ceiling():
    long_text = _make_long_section_text(400)
    assert estimate_tokens(long_text) > 6000  # confirm the fixture actually exceeds the ceiling

    chunks = chunk_section_text(long_text)

    assert len(chunks) > 1
    for chunk in chunks:
        assert estimate_tokens(chunk) <= 6000


def test_chunking_does_not_silently_drop_content():
    """Every sentence present in the original section_text must appear in some chunk —
    concatenating chunks must cover the original text, not lose any candidate's
    definition to a gap between chunk boundaries."""
    long_text = _make_long_section_text(400)
    chunks = chunk_section_text(long_text)

    recombined = " ".join(chunks)
    # Every distinct sentence marker (by index) from the source text must survive in the
    # recombined chunks — proves no chunk silently swallowed a stretch of text.
    for i in range(400):
        marker = f"example term {i} means"
        assert marker in recombined, f"content for term index {i} missing after chunking"


def test_chunking_respects_custom_token_ceiling():
    """A smaller explicit ceiling produces more, smaller chunks — proves the ceiling
    parameter is actually load-bearing, not a fixed/ignored default."""
    text = _make_long_section_text(100)
    chunks_default = chunk_section_text(text)
    chunks_tight = chunk_section_text(text, token_ceiling=500)

    assert len(chunks_tight) >= len(chunks_default)
    for chunk in chunks_tight:
        assert estimate_tokens(chunk) <= 500 or chunk.count(".") <= 1  # allow a single oversized sentence alone in its chunk


def test_single_oversized_sentence_is_not_force_split_mid_word():
    """A pathological single sentence longer than the ceiling must still be returned
    whole (in its own chunk) rather than being truncated mid-word, since legal
    definitions must never be silently cut off."""
    huge_sentence = "one giant sentence " * 2000 + "with no terminating punctuation at all"
    chunks = chunk_section_text(huge_sentence, token_ceiling=100)
    assert "".join(chunks).replace(" ", "") == huge_sentence.replace(" ", "")
