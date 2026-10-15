"""Quoted amendment text (lex-au v0.10.0 <quotedStructure>) is not the amending Act's own law."""
from lexaugraph.complexity import compute_complexity
from lexaugraph.graph import LexAuGraph
from lexaugraph.loader import parse_act

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
INDEX_ENTRY = {
    "name": "Test Amendment Act 2012",
    "year": 2012,
    "number": 174,
    "effective_date": "2026-01-01",
    "xml_path": "test-amendment-act-2012.xml",
    "title_id": "C2012A00174",
}

XML = f"""<?xml version='1.0' encoding='UTF-8'?>
<akomaNtoso xmlns="{AKN_NS}">
  <act name="act">
    <meta>
      <identification source="#lex-au">
        <FRBRWork>
          <FRBRthis value="/akn/au/act/2012/174/!main"/>
          <FRBRuri value="/akn/au/act/2012/174"/>
          <FRBRdate date="2012" name="Generation"/>
          <FRBRauthor href="#parliament"/>
        </FRBRWork>
        <FRBRExpression>
          <FRBRthis value="/akn/au/act/2012/174/eng@2026-01-01/!main"/>
          <FRBRuri value="/akn/au/act/2012/174/eng@2026-01-01"/>
          <FRBRdate date="2026-01-01" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRlanguage language="eng"/>
        </FRBRExpression>
        <FRBRManifestation>
          <FRBRthis value="/akn/au/act/2012/174/eng@2026-01-01/!main.akn"/>
          <FRBRuri value="/akn/au/act/2012/174/eng@2026-01-01/!main.akn"/>
          <FRBRdate date="2026-06-19" name="Generation"/>
          <FRBRauthor href="#lex-au"/>
        </FRBRManifestation>
      </identification>
    </meta>
    <body>
      <section eId="sec-1"><num>1</num><heading>Short title</heading>
        <content><p>This Act is the Test Amendment Act 2012.</p></content>
      </section>
    </body>
    <attachments>
      <attachment>
        <hcontainer name="schedule" eId="schedule-1">
          <hcontainer name="item" eId="schedule-1__item-1">
            <content><p>After section 149B insert:</p></content>
            <quotedStructure>
              <section eId="schedule-1__item-1__qstr-1__sec-149C">
                <num>149C</num><heading>Default fund terms</heading>
                <content>
                  <p>A modern award must comply with <ref href="#sec-149D">section 149D</ref>.</p>
                  <p><term refersTo="#term-default-fund">default fund</term>
                     <def>a fund nominated by the modern award</def></p>
                </content>
              </section>
            </quotedStructure>
          </hcontainer>
        </hcontainer>
      </attachment>
    </attachments>
  </act>
</akomaNtoso>
"""


def _graph(tmp_path):
    path = tmp_path / "test-amendment-act-2012.xml"
    path.write_text(XML, encoding="utf-8")
    data = parse_act(path, INDEX_ENTRY)
    g = LexAuGraph()
    g.add_act_data(data)
    return data, g


def test_quoted_section_is_tagged_not_dropped(tmp_path):
    data, _ = _graph(tmp_path)
    by_type = {s.eid: s.provision_type for s in data.sections}
    assert by_type["sec-1"] == "section"
    assert by_type["schedule-1__item-1__qstr-1__sec-149C"] == "quoted"


def test_quoted_text_creates_no_ref_edges(tmp_path):
    data, _ = _graph(tmp_path)
    quoted_ids = {s.node_id for s in data.sections if s.provision_type == "quoted"}
    assert quoted_ids
    assert not [r for r in data.ref_edges if r.source_id in quoted_ids]


def test_quoted_definitions_are_not_extracted(tmp_path):
    data, _ = _graph(tmp_path)
    assert [t.term for t in data.defined_terms] == []


def test_quoted_sections_are_not_citation_targets(tmp_path):
    _, g = _graph(tmp_path)
    index = g._section_number_index.get("/akn/au/act/2012/174", {})
    assert "149C" not in index
    assert "1" in index


def test_quoted_text_is_excluded_from_complexity(tmp_path):
    _, g = _graph(tmp_path)
    (row,) = compute_complexity(g.graph, centrality={})
    text = " ".join(
        d["text"] for _, d in g.graph.nodes(data=True) if d.get("type") == "section"
        and d.get("provision_type") != "quoted"
    )
    assert row.word_count == len(text.split())
