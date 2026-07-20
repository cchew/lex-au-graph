from pathlib import Path
import pytest
from lexaugraph.loader import parse_act, load_corpus

FIXTURES = Path(__file__).parent / "fixtures"

INDEX_ENTRY = {
    "name": "Privacy Act 1988",
    "year": 1988,
    "number": 119,
    "effective_date": "2026-06-04",
    "xml_path": "xml/privacy-act-1988.xml",
}


def test_parse_act_returns_act_node():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    assert data.act_node.frbr_uri == "/akn/au/act/1988/119"
    assert data.act_node.title == "Privacy Act 1988"
    assert data.act_node.year == 1988
    assert data.act_node.compilation_date == "2026-06-04"


def test_parse_act_extracts_sections():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    eids = [s.eid for s in data.sections]
    assert "part-I__sec-6" in eids
    assert "part-I__sec-13" in eids


def test_parse_act_section_has_heading_and_text():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    sec6 = next(s for s in data.sections if s.eid == "part-I__sec-6")
    assert sec6.heading == "Interpretation"
    assert "personal information" in sec6.text


def test_parse_act_extracts_defined_terms():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    terms = {t.term for t in data.defined_terms}
    assert "personal information" in terms
    assert "sensitive information" in terms


def test_parse_act_defined_term_links_to_section():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    pi = next(t for t in data.defined_terms if t.term == "personal information")
    assert pi.section_eid == "part-I__sec-6"
    assert "identified individual" in pi.definition_text


def test_parse_act_defined_term_display_case():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    pi = next(t for t in data.defined_terms if t.term == "personal information")
    assert pi.display_term == "personal information"


def test_parse_act_extracts_same_act_ref():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    same_act_refs = [r for r in data.ref_edges if not r.is_cross_act]
    assert any(r.target_href == "#part-I__sec-6" for r in same_act_refs)


def test_parse_act_extracts_cross_act_ref():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    cross_act_refs = [r for r in data.ref_edges if r.is_cross_act]
    assert any("Freedom of Information Act 1982" in r.ref_text for r in cross_act_refs)


def test_parse_act_extracts_untagged_prose_citation():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    untagged_refs = [r for r in data.ref_edges if r.matched_title is not None]
    assert any(r.matched_title == "freedom of information act 1982" for r in untagged_refs)


def test_untagged_prose_citation_has_null_target_href():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    untagged_refs = [r for r in data.ref_edges if r.matched_title is not None]
    foi_ref = next(r for r in untagged_refs if r.matched_title == "freedom of information act 1982")
    assert foi_ref.target_href is None
    assert foi_ref.is_cross_act is True


def test_tagged_ref_text_still_stored_raw_with_the_prefix():
    # Confirms the tagged-ref extraction path is untouched: ref_text keeps "the ",
    # matched_title is None (normalization happens at resolution time in graph.py, not here).
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    tagged_refs = [r for r in data.ref_edges if r.is_cross_act and r.matched_title is None]
    assert any(r.ref_text == "the Freedom of Information Act 1982" for r in tagged_refs)


INTRA_ACT_INDEX_ENTRY = {
    "name": "Sample Act 1999",
    "year": 1999,
    "number": 1,
    "effective_date": "2026-07-18",
    "xml_path": "xml/intra-act-citation-sample.xml",
}


def test_parse_act_extracts_intra_act_citation():
    data = parse_act(FIXTURES / "intra-act-citation-sample.xml", INTRA_ACT_INDEX_ENTRY)
    intra_act_refs = [r for r in data.ref_edges if r.matched_section is not None]
    assert any(r.matched_section == "6" and not r.is_cross_act for r in intra_act_refs)


def test_intra_act_citation_has_null_target_href_and_matched_title():
    data = parse_act(FIXTURES / "intra-act-citation-sample.xml", INTRA_ACT_INDEX_ENTRY)
    intra_act_refs = [r for r in data.ref_edges if r.matched_section is not None]
    ref = next(r for r in intra_act_refs if r.ref_text == "section 6")
    assert ref.target_href is None
    assert ref.matched_title is None
    assert ref.is_cross_act is False


def test_intra_act_citation_excludes_bare_subsection_and_tagged_ref_text():
    data = parse_act(FIXTURES / "intra-act-citation-sample.xml", INTRA_ACT_INDEX_ENTRY)
    intra_act_refs = [r for r in data.ref_edges if r.matched_section is not None]
    # "Subsection (2)" (no number) never becomes a match; the tagged <ref>'s
    # "section 6" text is excluded from prose extraction (already captured by
    # the existing tagged-ref pass, which sets matched_section=None, not this one).
    # "section 6" (x2) + "subsection 6(2)" + "Sections 6 and 13" (2 edges: one per
    # named section) = 5.
    assert len(intra_act_refs) == 5
    assert all(r.ref_text != "Subsection (2)" for r in intra_act_refs)


def test_subsection_pinpoint_extracts_base_section_number():
    data = parse_act(FIXTURES / "intra-act-citation-sample.xml", INTRA_ACT_INDEX_ENTRY)
    intra_act_refs = [r for r in data.ref_edges if r.matched_section is not None]
    ref = next(r for r in intra_act_refs if r.ref_text == "subsection 6(2)")
    assert ref.matched_section == "6"


def test_multi_section_list_citation_produces_one_ref_edge_per_section():
    data = parse_act(FIXTURES / "intra-act-citation-sample.xml", INTRA_ACT_INDEX_ENTRY)
    intra_act_refs = [r for r in data.ref_edges if r.matched_section is not None]
    multi_section_refs = [r for r in intra_act_refs if r.ref_text == "Sections 6 and 13"]
    assert len(multi_section_refs) == 2
    assert {r.matched_section for r in multi_section_refs} == {"6", "13"}
    # Both edges carry the same full ref_text (the raw citing phrase), even
    # though each targets a different section.
    assert all(r.ref_text == "Sections 6 and 13" for r in multi_section_refs)
    assert all(not r.is_cross_act for r in multi_section_refs)
    assert all(r.target_href is None and r.matched_title is None for r in multi_section_refs)
