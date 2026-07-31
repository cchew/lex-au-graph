from __future__ import annotations
import json
from types import SimpleNamespace

from lexaugraph.models import RelationType
from lexaugraph.relation_classifier import (
    classify_relation,
    classify_relation_llm,
    classify_relation_regex,
)


def _fake_client(response_text: str):
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text=response_text)])
    return SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: response))


def _raising_client():
    def _raise(**kwargs):
        raise AssertionError("LLM should not be called when the regex result is unambiguous")
    return SimpleNamespace(messages=SimpleNamespace(create=_raise))


# --- classify_relation_regex ---

def test_regex_detects_amends():
    section_text = (
        "Sub-section (2) of section forty-two of the Superannuation Act 1976 "
        "is amended by omitting the word 'three'."
    )
    result = classify_relation_regex("Superannuation Act 1976", section_text)
    assert result is not None
    assert result.relation == RelationType.AMENDS
    assert result.relation_confidence == 0.85


def test_regex_detects_repeals():
    section_text = "Section 6 of the Fair Work Act 2009 is repealed."
    result = classify_relation_regex("Fair Work Act 2009", section_text)
    assert result is not None
    assert result.relation == RelationType.REPEALS
    assert result.relation_confidence == 0.85


def test_regex_detects_references_definition():
    section_text = "The term employee has the same meaning as in the Fair Work Act 2009."
    result = classify_relation_regex("Fair Work Act 2009", section_text)
    assert result is not None
    assert result.relation == RelationType.REFERENCES_DEFINITION
    assert result.relation_confidence == 0.85


def test_regex_defaults_to_cites_when_no_verb_nearby():
    section_text = "This section operates subject to the Fair Work Act 2009 for all purposes."
    result = classify_relation_regex("Fair Work Act 2009", section_text)
    assert result is not None
    assert result.relation == RelationType.CITES
    assert result.relation_confidence == 0.75


def test_regex_excludes_amendment_act_title_text_from_window():
    # "Amendment" appears inside the citation's own title, not in the surrounding
    # context -- must not be misread as an AMENDS relation.
    section_text = "This section is taken to have effect subject to the Superannuation Amendment Act 1988 accordingly."
    result = classify_relation_regex("Superannuation Amendment Act 1988", section_text)
    assert result is not None
    assert result.relation == RelationType.CITES


def test_regex_returns_none_when_ambiguous():
    section_text = "The Fair Work Act 2009 is amended and also repealed in part by this Act."
    result = classify_relation_regex("Fair Work Act 2009", section_text)
    assert result is None


def test_regex_returns_confident_cites_when_ref_text_not_found():
    result = classify_relation_regex("Fair Work Act 2009", "Some unrelated text.")
    assert result is not None
    assert result.relation == RelationType.CITES
    assert result.relation_confidence == 0.75


# --- classify_relation_llm ---

def test_llm_parses_valid_response():
    client = _fake_client(json.dumps({"relation": "amends"}))
    result = classify_relation_llm("Fair Work Act 2009", "ambiguous context", client)
    assert result.relation == RelationType.AMENDS
    assert result.relation_confidence == 0.6


def test_llm_invalid_json_defaults_to_cites_low_confidence():
    client = _fake_client("not valid json")
    result = classify_relation_llm("Fair Work Act 2009", "context", client)
    assert result.relation == RelationType.CITES
    assert result.relation_confidence == 0.3


def test_llm_unknown_relation_value_defaults_to_cites_low_confidence():
    client = _fake_client(json.dumps({"relation": "nonsense"}))
    result = classify_relation_llm("Fair Work Act 2009", "context", client)
    assert result.relation == RelationType.CITES
    assert result.relation_confidence == 0.3


# --- classify_relation (hybrid entry point) ---

def test_hybrid_skips_llm_when_regex_confident():
    section_text = "Section 6 of the Fair Work Act 2009 is repealed."
    result = classify_relation("Fair Work Act 2009", section_text, _raising_client())
    assert result.relation == RelationType.REPEALS
    assert result.relation_confidence == 0.85


def test_hybrid_falls_back_to_llm_when_ambiguous():
    section_text = "The Fair Work Act 2009 is amended and also repealed in part by this Act."
    client = _fake_client(json.dumps({"relation": "amends"}))
    result = classify_relation("Fair Work Act 2009", section_text, client)
    assert result.relation == RelationType.AMENDS
    assert result.relation_confidence == 0.6


def test_hybrid_ambiguous_without_client_defaults_to_cites_low_confidence():
    section_text = "The Fair Work Act 2009 is amended and also repealed in part by this Act."
    result = classify_relation("Fair Work Act 2009", section_text, None)
    assert result.relation == RelationType.CITES
    assert result.relation_confidence == 0.3
