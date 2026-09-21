from pathlib import Path
import pytest
from lexaugraph.loader import parse_act, load_corpus
from lexaugraph.models import RelationType

FIXTURES = Path(__file__).parent / "fixtures"

INDEX_ENTRY = {
    "name": "Privacy Act 1988",
    "year": 1988,
    "number": 119,
    "effective_date": "2026-06-04",
    "xml_path": "xml/privacy-act-1988.xml",
    "title_id": "C2004A03712",
}

RELATION_INDEX_ENTRY = {
    "name": "Superannuation Amendment Act 1988",
    "year": 1988,
    "number": 130,
    "effective_date": "2026-06-04",
    "xml_path": "relation-classification-sample.xml",
}


def test_parse_act_classifies_tagged_ref_relation_and_extraction_confidence():
    data = parse_act(FIXTURES / "relation-classification-sample.xml", RELATION_INDEX_ENTRY)
    tagged = next(r for r in data.ref_edges if r.target_href is not None and r.ref_text == "Superannuation Act 1976")
    assert tagged.relation == RelationType.REPEALS
    assert tagged.extraction_confidence == 0.95


def test_parse_act_classifies_prose_citation_relation_and_extraction_confidence():
    data = parse_act(FIXTURES / "relation-classification-sample.xml", RELATION_INDEX_ENTRY)
    prose = next(r for r in data.ref_edges if r.matched_title == "fair work act 2009")
    assert prose.relation == RelationType.AMENDS
    assert prose.extraction_confidence == 0.7


def test_parse_act_classifies_intra_act_citation_relation_and_extraction_confidence():
    data = parse_act(FIXTURES / "relation-classification-sample.xml", RELATION_INDEX_ENTRY)
    intra = next(r for r in data.ref_edges if r.matched_section == "3")
    assert intra.relation == RelationType.CITES
    assert intra.extraction_confidence == 0.6


def test_parse_act_without_client_classifies_every_ref_edge():
    # No client passed -- must not attempt any network call (this fixture has no
    # ambiguous citations, so this also implicitly proves the whole pipeline runs
    # end-to-end with client=None, matching every existing call site in this file).
    data = parse_act(FIXTURES / "relation-classification-sample.xml", RELATION_INDEX_ENTRY)
    assert len(data.ref_edges) > 0
    assert all(r.relation is not None for r in data.ref_edges)


def test_parse_act_returns_act_node():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    assert data.act_node.frbr_uri == "/akn/au/act/1988/119"
    assert data.act_node.title == "Privacy Act 1988"
    assert data.act_node.year == 1988
    assert data.act_node.compilation_date == "2026-06-04"


def test_parse_act_reads_title_id_from_index_entry():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    assert data.act_node.title_id == "C2004A03712"
    assert data.act_node.legislation_url == "https://www.legislation.gov.au/C2004A03712/latest/text"


def test_parse_act_title_id_defaults_to_none_when_absent():
    entry_without_title_id = {k: v for k, v in INDEX_ENTRY.items() if k != "title_id"}
    data = parse_act(FIXTURES / "privacy-act-1988.xml", entry_without_title_id)
    assert data.act_node.title_id is None
    assert data.act_node.legislation_url is None


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


TERM_OPERATOR_INDEX_ENTRY = {
    "name": "Sample Sea Protection Act 2006",
    "year": 2006,
    "number": 22,
    "effective_date": "2026-06-04",
    "xml_path": "term-operator-sample.xml",
}


def test_defined_term_definition_text_keeps_means_operator():
    # The AKN <def> element wraps only the definiens; the operator (" means ")
    # lives in the <term>'s tail and was being dropped.
    data = parse_act(FIXTURES / "term-operator-sample.xml", TERM_OPERATOR_INDEX_ENTRY)
    af = next(t for t in data.defined_terms if t.term == "approved form")
    assert af.definition_text == "means a form approved by the Minister."


def test_defined_term_definition_text_keeps_inclusive_operator():
    data = parse_act(FIXTURES / "term-operator-sample.xml", TERM_OPERATOR_INDEX_ENTRY)
    fv = next(t for t in data.defined_terms if t.term == "foreign vessel")
    assert fv.definition_text == "includes a vessel registered outside Australia."


def test_defined_term_definition_text_keeps_pointer_operator():
    data = parse_act(FIXTURES / "term-operator-sample.xml", TERM_OPERATOR_INDEX_ENTRY)
    rp = next(t for t in data.defined_terms if t.term == "relevant period")
    assert rp.definition_text == "has the meaning given by section 7."


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


UNRESOLVED_REF_INDEX_ENTRY = {
    "name": "Sample Act 1999",
    "year": 1999,
    "number": 1,
    "effective_date": "2026-09-21",
    "xml_path": "unresolved-ref-sample.xml",
}


def test_ref_with_unresolved_class_reads_target_class():
    # lex-au's converter now stamps a deterministic stub href onto every
    # unresolved cross-Act <ref>, alongside its existing class="unresolved"
    # marker. loader.py must read that marker into RefEdge.target_class so
    # graph.py can tell a stub href apart from a genuinely resolved one.
    data = parse_act(FIXTURES / "unresolved-ref-sample.xml", UNRESOLVED_REF_INDEX_ENTRY)
    unresolved = next(r for r in data.ref_edges if r.target_href == "/akn/au/act/some-act-name-1999")
    assert unresolved.target_class == "unresolved"


def test_ref_without_class_attribute_leaves_target_class_none():
    # A ref with a real, resolved href never carries class="unresolved" --
    # target_class must be None (not "", not missing the attribute check),
    # so _resolve_ref's href-acceptance branch is unaffected for this case.
    data = parse_act(FIXTURES / "unresolved-ref-sample.xml", UNRESOLVED_REF_INDEX_ENTRY)
    resolved = next(r for r in data.ref_edges if r.target_href == "/akn/au/act/2001/50")
    assert resolved.target_class is None


DUPLICATE_EID_WITH_REF_INDEX_ENTRY = {
    "name": "Sample Act 1999",
    "year": 1999,
    "number": 1,
    "effective_date": "2026-09-21",
    "xml_path": "duplicate-eid-with-ref-sample.xml",
}


def test_citation_in_second_duplicate_eid_section_attributed_to_correct_node():
    # Real-corpus bug: occurrence used to only get set later, in graph.py's
    # _add_act_nodes -- but each RefEdge captures source_id=node.node_id at
    # PARSE time, before that later step ever runs. So a citation living in
    # the SECOND (or later) occurrence of a duplicate-eId section was always
    # captured with the FIRST occurrence's (unsuffixed) node_id -- the wrong
    # section entirely. _parse_sections must set node.occurrence before
    # building any RefEdge, so the citation lands on the right node from the
    # start.
    data = parse_act(FIXTURES / "duplicate-eid-with-ref-sample.xml", DUPLICATE_EID_WITH_REF_INDEX_ENTRY)

    first, second = (s for s in data.sections if s.eid == "part-I__sec-6")
    assert first.occurrence == 1
    assert second.occurrence == 2
    assert first.node_id != second.node_id

    ref = next(r for r in data.ref_edges if r.target_href == "#part-I__sec-13")
    assert ref.source_id == second.node_id
    assert ref.source_id != first.node_id


def test_extract_defined_terms_classifies_entity_type():
    index_entry = {
        "name": "Sample Registrar Act 1961", "year": 1961, "number": 12,
        "effective_date": "2026-06-04", "xml_path": "xml/registrar-entity-sample.xml",
    }
    act_data = parse_act(FIXTURES / "registrar-entity-sample.xml", index_entry)
    by_term = {t.term: t for t in act_data.defined_terms}
    assert by_term["registrar"].entity_type == "registrar"
    assert by_term["purpose"].entity_type is None
