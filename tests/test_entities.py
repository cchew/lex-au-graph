from lexaugraph.entities import OFFICE_KEYWORDS, classify_entity_type


def test_office_keywords_contains_all_eleven_categories():
    assert OFFICE_KEYWORDS == {
        "secretary", "commissioner", "minister", "tribunal", "registrar",
        "agency", "authority", "regulator", "ombudsman", "department", "court",
    }


def test_classify_entity_type_each_keyword_matches_itself():
    for keyword in OFFICE_KEYWORDS:
        assert classify_entity_type(keyword.capitalize()) == keyword


def test_classify_entity_type_no_match_returns_none():
    assert classify_entity_type("purpose") is None
    assert classify_entity_type("personal information") is None


def test_classify_entity_type_multi_keyword_longest_wins():
    # "Department" (10 chars) and "Authority" (9 chars) both appear as whole
    # words; longest/most specific keyword wins per spec.
    assert classify_entity_type("Department Authority") == "department"


def test_classify_entity_type_real_false_positives_from_corpus_check():
    # Confirmed real corpus false-positives under naive substring matching —
    # explicit regression cases per the spec's Testing section.
    assert classify_entity_type("Regulatory Powers Act") is None
    assert classify_entity_type("Departmental employee") is None
    assert classify_entity_type("Ministerial Council") is None


def test_classify_entity_type_qualified_term_matches_embedded_keyword():
    assert classify_entity_type("Commissioner of Taxation") == "commissioner"
    assert classify_entity_type("Federal Court") == "court"
