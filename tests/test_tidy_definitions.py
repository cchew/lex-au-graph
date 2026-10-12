"""tidy_definitions: collapse duplicate-looking cards, keep genuine multi-meaning terms."""
from lexaugraph.models import DefinitionResult
from lexaugraph.resolver import _is_internal_pointer, tidy_definitions

ACT = "/akn/au-nsw/act/2002/71"


def _d(text: str, eid: str, act: str = ACT, scope: str = "act") -> DefinitionResult:
    return DefinitionResult("t", "t", text, act, eid, "Some Act", scope)


def test_internal_pointer_is_dropped_when_the_act_has_the_real_definition() -> None:
    got = tidy_definitions([_d("has the meaning given by section 5.", "sec-3"), _d("means information about a person.", "sec-5")])
    assert [d.section_eid for d in got] == ["sec-5"]


def test_lone_pointer_is_kept() -> None:
    got = tidy_definitions([_d("has the meaning given by section 5.", "sec-3")])
    assert len(got) == 1


def test_pointer_to_another_act_is_kept_alongside() -> None:
    other = _d("has the same meaning as in the Privacy Act 1988.", "sec-3")
    got = tidy_definitions([other, _d("means a thing.", "sec-5")])
    assert len(got) == 2


def test_includes_supplement_merges_into_the_means_definition_of_the_same_section() -> None:
    got = tidy_definitions([
        _d("means information about a person.", "sec-4"),
        _d("includes such things as fingerprints.", "sec-4"),
    ])
    assert len(got) == 1
    assert got[0].definition_text == "means information about a person. includes such things as fingerprints."


def test_different_sections_stay_separate() -> None:
    got = tidy_definitions([_d("means A.", "sec-4"), _d("includes B.", "sec-9")])
    assert len(got) == 2


def test_multi_meaning_terms_in_different_parts_are_kept() -> None:
    got = tidy_definitions([
        _d("means the amount in Division 1.", "part-1__dvs-1__sec-5"),
        _d("means the amount in Division 2.", "part-1__dvs-2__sec-9"),
    ])
    assert len(got) == 2


def test_other_acts_are_untouched_and_order_is_stable() -> None:
    a = _d("means X.", "sec-1", "/akn/au/act/1/1")
    b = _d("means Y.", "sec-1", "/akn/au-vic/act/2/2")
    assert [d.act_frbr_uri for d in tidy_definitions([a, b])] == ["/akn/au/act/1/1", "/akn/au-vic/act/2/2"]


def test_input_results_are_not_mutated() -> None:
    first = _d("means A.", "sec-4")
    tidy_definitions([first, _d("includes B.", "sec-4")])
    assert first.definition_text == "means A."


def test_pointer_detector() -> None:
    assert _is_internal_pointer(", see section 4A.")
    assert _is_internal_pointer("has the same meaning as in section 134V.")
    assert not _is_internal_pointer("has the same meaning as in the Health Services Act 1988.")
    assert not _is_internal_pointer("means information or an opinion about an identified individual")


def test_resolver_lists_jurisdictions_cth_first() -> None:
    from lexaugraph.graph import LexAuGraph
    from lexaugraph.models import ActData, ActNode
    from lexaugraph.resolver import DefinitionResolver

    g = LexAuGraph()
    for uri in ("/akn/au-vic/act/2014/60", "/akn/au/act/1988/119", "/akn/au-act/act/2014/24"):
        g.add_act_data(ActData(act_node=ActNode(frbr_uri=uri, title=uri, year=2000), sections=[], defined_terms=[], ref_edges=[]))
    assert DefinitionResolver(g).jurisdictions() == ["Cth", "ACT", "Vic"]
