"""Two corpus Acts sharing one FRBR work URI (real case: SR 1994 No. 57, the SIS Regulations, and
Act No. 57 of 1994, both minted /akn/au/act/1994/57 by lex-au) must stay two graph Acts."""
import json
from pathlib import Path

import pytest

from lexaugraph.graph import LexAuGraph
from lexaugraph.loader import assign_act_ids, load_corpus
from lexaugraph.resolver import DefinitionResolver

URI = "/akn/au/act/1994/57"

_XML = """<?xml version='1.0' encoding='UTF-8'?>
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <act name="act">
    <meta><identification source="#lex-au">
      <FRBRWork><FRBRthis value="{uri}/!main"/><FRBRuri value="{uri}"/>
        <FRBRdate date="1994-01-01" name="Generation"/><FRBRauthor href="#parliament"/></FRBRWork>
      <FRBRExpression><FRBRthis value="{uri}/eng@{d}/!main"/><FRBRuri value="{uri}/eng@{d}"/>
        <FRBRdate date="{d}" name="Generation"/><FRBRauthor href="#parliament"/>
        <FRBRlanguage language="eng"/></FRBRExpression>
    </identification></meta>
    <body>{body}</body>
  </act>
</akomaNtoso>
"""

_REGS_BODY = """
    <part eId="part-1"><num>1</num><heading>Preliminary</heading>
      <section eId="part-1__sec-1.03"><num>1.03</num><heading>Definitions</heading>
        <content><p><term refersTo="#term-fund">fund</term> means <def>a superannuation fund.</def></p></content>
      </section>
      <section eId="part-1__sec-1.05"><num>1.05</num><heading>Meaning of member</heading>
        <content><p><term refersTo="#term-member--part-1__sec-1.05">member</term> means <def>a person in the fund.</def></p></content>
      </section>
    </part>"""

_ACT_BODY = """
    <section eId="sec-1"><num>1</num><heading>Short title</heading>
      <content><p>This Act may be cited as the Training Guarantee (Administration) Amendment Act 1994.</p></content>
    </section>
    <section eId="sec-3"><num>3</num><heading>Interpretation</heading>
      <content><p>Section 3 of the Principal Act is amended.</p></content>
    </section>"""

REGS = ("superannuation-industry-(supervision)-regulations-1994", "Superannuation Industry (Supervision) Regulations 1994", "F1996B00580", "2026-07-01", _REGS_BODY)
ACT = ("training-guarantee-(administration)-amendment-act-1994", "Training Guarantee (Administration) Amendment Act 1994", "C2004A04733", "1994-04-07", _ACT_BODY)


def _corpus(tmp_path: Path, order) -> Path:
    (tmp_path / "xml").mkdir()
    acts = {}
    for slug, name, title_id, d, body in order:
        (tmp_path / "xml" / f"{slug}.xml").write_text(_XML.format(uri=URI, d=d, body=body))
        acts[slug] = {"name": name, "title_id": title_id, "year": 1994, "number": 57,
                      "effective_date": d, "xml_path": f"xml/{slug}.xml"}
    (tmp_path / "index.json").write_text(json.dumps({"acts": acts, "structure_version": 2}))
    return tmp_path


@pytest.mark.parametrize("order", [(REGS, ACT), (ACT, REGS)], ids=["regs-first", "act-first"])
def test_colliding_work_uris_load_as_two_acts(tmp_path, order) -> None:
    acts = {a.act_node.title: a for a in load_corpus(_corpus(tmp_path, order))}
    regs = acts[REGS[1]]
    act = acts[ACT[1]]
    # The Act (C title id) keeps the plain work URI; the instrument is disambiguated by its title id.
    assert act.act_node.frbr_uri == URI
    assert regs.act_node.frbr_uri == f"{URI}~F1996B00580"
    assert {s.act_frbr_uri for s in regs.sections} == {regs.act_node.frbr_uri}
    assert {t.act_frbr_uri for t in regs.defined_terms} == {regs.act_node.frbr_uri}
    assert not act.defined_terms


def test_graph_keeps_terms_and_sections_apart(tmp_path) -> None:
    g = LexAuGraph()
    g.build(_corpus(tmp_path, (REGS, ACT)))
    r = DefinitionResolver(g)
    regs_id = r.act_node_id(URI, "F1996B00580")
    act_id = r.act_node_id(URI, "C2004A04733")
    assert (regs_id, act_id) == (f"{URI}~F1996B00580", URI)
    assert g.graph.nodes[act_id]["title"] == ACT[1]
    assert g.graph.nodes[regs_id]["title"] == REGS[1]
    assert r.get_act_definitions(act_id, include_local=True) == []
    rows = r.get_act_definitions(regs_id, include_local=True)
    assert sorted((x["term"], x["scope"]) for x in rows) == [("fund", "act"), ("member", "part-1__sec-1.05")]
    act_secs = {n for n in g.graph.successors(act_id)}
    assert act_secs == {f"{URI}#sec-1", f"{URI}#sec-3"}


def test_act_node_id_without_collision_is_the_work_uri(tmp_path) -> None:
    g = LexAuGraph()
    g.build(_corpus(tmp_path, (REGS,)))
    r = DefinitionResolver(g)
    assert r.act_node_id(URI, "F1996B00580") == URI
    assert r.act_node_id(URI) == URI
    assert r.act_node_id("/akn/au/act/2000/1", "C2000A00001") == "/akn/au/act/2000/1"


def test_assign_act_ids_is_order_independent_and_only_touches_collisions() -> None:
    entries = [
        ("b-regs", {"title_id": "F2"}, "/akn/au/act/2000/1"),
        ("a-act", {"title_id": "C1"}, "/akn/au/act/2000/1"),
        ("other", {"title_id": "C9"}, "/akn/au/act/2001/5"),
        ("x", {"title_id": "F7"}, "/akn/au/act/2002/3"),
        ("y", {"title_id": "F8"}, "/akn/au/act/2002/3"),
    ]
    ids = assign_act_ids(entries)
    assert ids == assign_act_ids(list(reversed(entries)))
    assert ids["a-act"] == "/akn/au/act/2000/1"
    assert ids["b-regs"] == "/akn/au/act/2000/1~F2"
    assert ids["other"] == "/akn/au/act/2001/5"
    # no Act among them: the first slug keeps the plain URI
    assert (ids["x"], ids["y"]) == ("/akn/au/act/2002/3", "/akn/au/act/2002/3~F8")


def test_add_act_data_rejects_a_different_act_at_an_existing_id(tmp_path) -> None:
    from lexaugraph.loader import parse_act
    c = _corpus(tmp_path, (REGS, ACT))
    g = LexAuGraph()
    g.add_act_data(parse_act(c / "xml" / f"{REGS[0]}.xml", json.loads((c / "index.json").read_text())["acts"][REGS[0]]))
    with pytest.raises(ValueError, match="already holds"):
        g.add_act_data(parse_act(c / "xml" / f"{ACT[0]}.xml", json.loads((c / "index.json").read_text())["acts"][ACT[0]]))
