from __future__ import annotations

import lxml.etree as ET

from lexaugraph.citations import (
    extract_intra_act_citations,
    extract_prose_citations,
    extract_section_number,
    extract_section_numbers,
    is_self_citation,
    normalize_title,
)

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def _section(body: str) -> ET._Element:
    xml = f"""<section xmlns="{AKN_NS}" eId="sec-1">
      <content>
        {body}
      </content>
    </section>""".encode("utf-8")
    return ET.fromstring(xml)


# --- normalize_title ---

def test_normalize_title_strips_leading_the_and_extracts_year():
    assert normalize_title("the Corporations Act 2001") == ("corporations act 2001", 2001)


def test_normalize_title_strips_this_and_that():
    assert normalize_title("This Fair Work Act 2009") == ("fair work act 2009", 2009)
    assert normalize_title("that Migration Act 1958") == ("migration act 1958", 1958)


def test_normalize_title_matches_title_index_key_format():
    # Regression test for the bug: raw AKN ref text keeps "the ", title-index keys don't.
    act_title_key = "corporations act 2001"  # equivalent to ActNode.title.lower()
    ref_text = "the Corporations Act 2001"
    normalized = normalize_title(ref_text)
    assert normalized is not None
    assert normalized[0] == act_title_key


def test_normalize_title_rejects_missing_year():
    assert normalize_title("Corporations Act") is None


def test_normalize_title_rejects_single_word_before_year():
    assert normalize_title("Act 2001") is None


def test_normalize_title_is_idempotent():
    once = normalize_title("the Corporations Act 2001")
    twice = normalize_title(once[0])
    assert once == twice


def test_normalize_title_normalizes_curly_apostrophe():
    # ’ = right single quotation mark (curly apostrophe), as may appear in
    # some AKN XML sources for titles like "Veterans’ Entitlements Act 1986"
    curly = "the Veterans’ Entitlements Act 1986"
    straight = "the Veterans' Entitlements Act 1986"
    assert normalize_title(curly) == normalize_title(straight)
    assert normalize_title(curly) == ("veterans' entitlements act 1986", 1986)


# --- is_self_citation ---

def test_is_self_citation_true_for_matching_normalized_title():
    assert is_self_citation("privacy act 1988", "Privacy Act 1988") is True


def test_is_self_citation_false_for_different_title():
    assert is_self_citation("corporations act 2001", "Privacy Act 1988") is False


# --- extract_prose_citations ---

def test_extract_prose_citations_finds_untagged_mention():
    section = _section("<p>This Act operates alongside the Fair Work Act 2009.</p>")
    assert extract_prose_citations(section) == ["Fair Work Act 2009"]


def test_extract_prose_citations_excludes_text_inside_ref_elements():
    section = _section(
        '<p>See also <ref href="">the Corporations Act 2001</ref> for details.</p>'
    )
    assert extract_prose_citations(section) == []


def test_extract_prose_citations_includes_tail_text_after_ref():
    section = _section(
        '<p>See <ref href="#sec-2">section 2</ref> and the Fair Work Act 2009.</p>'
    )
    assert extract_prose_citations(section) == ["Fair Work Act 2009"]


def test_extract_prose_citations_counts_duplicate_mentions():
    section = _section(
        "<p>Nothing in the Fair Work Act 2009 limits this section. "
        "Rights under the Fair Work Act 2009 continue to apply.</p>"
    )
    assert extract_prose_citations(section) == ["Fair Work Act 2009", "Fair Work Act 2009"]


def test_extract_prose_citations_matches_parenthetical_titles():
    section = _section(
        "<p>Payments under the Social Security (Administration) Act 1999 are affected.</p>"
    )
    assert extract_prose_citations(section) == ["Social Security (Administration) Act 1999"]


def test_extract_prose_citations_matches_titles_with_of_connector():
    # Real corpus title (see freedom-of-information-act-1982.xml fixture, Task 4)
    section = _section(
        "<p>This section does not limit the Freedom of Information Act 1982.</p>"
    )
    assert extract_prose_citations(section) == ["Freedom of Information Act 1982"]


def test_extract_prose_citations_matches_titles_with_and_connector():
    # Real corpus title: Competition and Consumer Act 2010 (lex-au v0.6.1 corpus)
    section = _section(
        "<p>Nothing here affects the Competition and Consumer Act 2010.</p>"
    )
    assert extract_prose_citations(section) == ["Competition and Consumer Act 2010"]


def test_extract_prose_citations_no_match_returns_empty_list():
    section = _section("<p>This section has no citations at all.</p>")
    assert extract_prose_citations(section) == []


def test_extract_prose_citations_matches_title_split_across_inline_runs():
    # Real corpus text: lex-au's inline-formatting pass (v0.6.0) sometimes puts a
    # hyphen in its own <i> run, e.g. "Territory (Self<i>-</i><i>Government) Act 1978"
    # in criminal-code-act-1995.xml. Regression test for the bug: _text_outside_refs
    # joined text/tail fragments with an artificial space, turning "Self-Government)"
    # into "Self - Government)" and truncating the match to "Government) Act 1978".
    section = _section(
        "<p>See the Australian Capital Territory "
        "(Self<i>-</i><i>Government) Act 1978</i> for details.</p>"
    )
    assert extract_prose_citations(section) == [
        "Australian Capital Territory (Self-Government) Act 1978"
    ]


def test_extract_prose_citations_matches_curly_apostrophe_title():
    # Real corpus text uses U+2019 (right single quotation mark), not a straight
    # apostrophe, e.g. "Veterans’ Entitlements Act 1986" in social-security-act-1991.xml.
    # Regression test for the bug: the citation pattern's word-char class didn't include
    # the curly apostrophe, so the match started mid-title at "Entitlements Act 1986".
    section = _section(
        "<p>A payment under the Veterans’ Entitlements Act 1986 is exempt.</p>"
    )
    assert extract_prose_citations(section) == ["Veterans’ Entitlements Act 1986"]


# --- extract_intra_act_citations ---


def test_intra_act_pattern_matches_section_reference():
    section = _section("<p>This section applies subject to section 6.</p>")
    assert extract_intra_act_citations(section) == ["section 6"]


def test_intra_act_pattern_matches_abbreviated_s_reference():
    section = _section("<p>See s 6 for definitions.</p>")
    assert extract_intra_act_citations(section) == ["s 6"]


def test_intra_act_pattern_matches_multi_section_list():
    section = _section("<p>Sections 26WD and 26WE apply.</p>")
    assert extract_intra_act_citations(section) == ["Sections 26WD and 26WE"]


def test_intra_act_pattern_matches_subsection_pinpoint():
    section = _section("<p>Subsection 26WD(2) applies.</p>")
    assert extract_intra_act_citations(section) == ["Subsection 26WD(2)"]


def test_intra_act_pattern_excludes_bare_subsection_with_no_number():
    section = _section("<p>Subsection (2) does not apply.</p>")
    assert extract_intra_act_citations(section) == []


def test_intra_act_pattern_excludes_text_inside_ref_elements():
    section = _section('<p>See also <ref href="#sec-6">section 6</ref> for definitions.</p>')
    assert extract_intra_act_citations(section) == []


def test_intra_act_pattern_counts_duplicate_mentions():
    section = _section(
        "<p>This section applies subject to section 6. "
        "Nothing in section 6 limits subsection 6(2).</p>"
    )
    assert extract_intra_act_citations(section) == ["section 6", "section 6", "subsection 6(2)"]


def test_intra_act_pattern_no_match_returns_empty_list():
    section = _section("<p>This section has no numbered citations at all.</p>")
    assert extract_intra_act_citations(section) == []


# --- extract_section_number ---


def test_extract_section_number_from_simple_reference():
    assert extract_section_number("section 6") == "6"


def test_extract_section_number_from_abbreviated_reference():
    assert extract_section_number("s 26WD") == "26WD"


def test_extract_section_number_from_subsection_pinpoint():
    assert extract_section_number("subsection 26WD(2)") == "26WD"


def test_extract_section_number_from_multi_section_list_returns_first_only():
    # v1 known limitation: only the first section in a list resolves (see plan Design notes).
    assert extract_section_number("sections 26WD and 26WE") == "26WD"


def test_extract_section_number_returns_none_for_no_match():
    assert extract_section_number("no number here") is None


# --- extract_section_numbers ---


def test_extract_section_numbers_from_simple_reference():
    assert extract_section_numbers("section 6") == ["6"]


def test_extract_section_numbers_from_abbreviated_reference():
    assert extract_section_numbers("s 26WD") == ["26WD"]


def test_extract_section_numbers_from_multi_section_list_returns_all():
    assert extract_section_numbers("sections 26WD and 26WE") == ["26WD", "26WE"]


def test_extract_section_numbers_from_subsection_pinpoint_strips_pinpoint():
    assert extract_section_numbers("subsection 26WD(2)") == ["26WD"]


def test_extract_section_numbers_from_multi_pinpoint_list_strips_each_pinpoint():
    # Pinpoint subsection suffixes like "(32)" and "(1)" must not be mistaken
    # for additional cited sections.
    assert extract_section_numbers("s 2(32) and 6(1)") == ["2", "6"]


def test_extract_section_numbers_returns_empty_list_for_no_match():
    assert extract_section_numbers("no number here") == []
