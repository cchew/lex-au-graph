from __future__ import annotations

import lxml.etree as ET

from lexaugraph.citations import extract_prose_citations, is_self_citation, normalize_title

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
