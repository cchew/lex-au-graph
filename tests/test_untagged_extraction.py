from __future__ import annotations

import lxml.etree as ET

from lexaugraph.loader import find_untagged_candidates, filter_by_recurrence

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def _wrap(body: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<akomaNtoso xmlns="{AKN_NS}">
  <act>
    <body>
      <section eId="sec-23">
        <content>
          {body}
        </content>
      </section>
    </body>
  </act>
</akomaNtoso>
""".encode("utf-8")


def test_untagged_p_with_no_children_matching_pattern_is_found():
    xml = _wrap(
        "<p>income support payment means a payment of:</p>"
        "<paragraph><content><p>(a) a pension; or</p></content></paragraph>"
    )
    root = ET.fromstring(xml)
    candidates = find_untagged_candidates(root)
    terms = [term for term, _ in candidates]
    assert "income support payment" in terms


def test_tagged_p_with_children_is_not_picked_up():
    xml = _wrap(
        '<p><term refersTo="#term-x">income support payment</term>'
        '<def>means a payment of a designated kind</def></p>'
    )
    root = ET.fromstring(xml)
    candidates = find_untagged_candidates(root)
    terms = [term for term, _ in candidates]
    assert "income support payment" not in terms
    assert candidates == []


def test_candidate_recurring_three_plus_times_survives_filter():
    xml = _wrap("<p>income support payment means a payment of:</p>")
    root = ET.fromstring(xml)
    candidates = find_untagged_candidates(root)
    full_text = (
        "income support payment means a payment of: a pension. "
        "The income support payment is assessed. "
        "An income support payment recipient must notify changes. "
        "The rate of income support payment varies."
    )
    kept = filter_by_recurrence(candidates, full_text)
    kept_terms = [term for term, _ in kept]
    assert "income support payment" in kept_terms


def test_candidate_recurring_zero_to_two_times_is_filtered_out():
    xml = _wrap("<p>rare obscure term means a thing of no consequence:</p>")
    root = ET.fromstring(xml)
    candidates = find_untagged_candidates(root)
    # Recurs only twice total (including the definition line itself) in full_text
    full_text = (
        "rare obscure term means a thing of no consequence: "
        "The rare obscure term is mentioned once more here."
    )
    kept = filter_by_recurrence(candidates, full_text)
    kept_terms = [term for term, _ in kept]
    assert "rare obscure term" not in kept_terms
