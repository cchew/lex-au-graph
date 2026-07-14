# Term Node-ID Collision MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `_add_act_nodes` from silently overwriting same-Act, same-term graph nodes when a term genuinely has multiple distinct meanings within one Act (real OPC drafting practice, confirmed 746 distinct colliding slugs across 107 Acts) — give `DefinedTermNode.node_id` an occurrence disambiguator.

**Architecture:** Add an `occurrence: int = 1` field to `DefinedTermNode` (default preserves today's node_id exactly for the non-colliding case — the vast majority of terms). `node_id` appends `__N` only when `occurrence > 1`. `_add_act_nodes` computes the occurrence number from a per-Act, per-slug counter as it iterates `act_data.defined_terms`, before calling `add_node`.

**Tech Stack:** Python 3.12, NetworkX, pytest. No new dependencies.

**Independent of the `lex-au` list-definition-truncation fix** — Tasks 1-3 use synthetic test fixtures and don't touch the real corpus, so they can be built and merged regardless of that fix's timeline. Task 4 (rebuild + real-corpus verification) depends on `lex-au`'s corpus fix landing first — see that task's stop point.

## Global Constraints

- Python ≥ 3.12, all type annotations required.
- Tests live in `tests/`, one file per source module. Run with `pytest` from the repo root (venv: `source .venv/bin/activate`).
- Full spec: `../../lex-au/repo/docs/superpowers/specs/2026-07-14-list-definition-truncation-design.md` (spec lives in the `lex-au` repo since that's where the paired fix originates; this plan implements the "node_id MVP" section of it).
- Commit after every task using `caveman-commit` conventions (Conventional Commits, imperative subject ≤50 chars).
- Do not change `resolve_definition()` — it is intentionally Act-scoped, first-match-only, and not used by `term-comparison` (which calls `find_all_definitions()` exclusively via its `/definitions` endpoint). Out of scope per the spec.
- Do not touch `add_defined_term()` (the LLM-extraction backfill path) in this plan — it constructs a single `DefinedTermNode` with a fresh, uncounted `occurrence` default, so a term backfilled via that path into an Act that already has a same-slug node in the graph could still collide. This is a narrower, separate path from the bulk-extraction collision this MVP targets, not covered by the spec's 746-slug count, and not actioned here — note it as a known follow-up if it's ever observed in practice.

---

## Task 1: `DefinedTermNode.occurrence` + disambiguated `node_id`

**Files:**
- Modify: `src/lexaugraph/models.py:26-36` (`DefinedTermNode` class)
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `DefinedTermNode.occurrence: int = 1` (new field, default preserves existing behavior) and updated `node_id` property. Consumed by Task 2.

### Step 1: Write the failing tests

Add to `tests/test_models.py`, after `test_defined_term_node_id` (after line 25):

```python
def test_defined_term_node_id_default_occurrence_unchanged():
    """Default occurrence=1 must produce exactly today's node_id -- no
    suffix -- so every non-colliding term (the vast majority) is unaffected."""
    t = DefinedTermNode(
        term="personal information",
        display_term="personal information",
        act_frbr_uri="/akn/au/act/1988/119",
        section_eid="part-I__sec-6",
        definition_text="information or an opinion about an identified individual",
    )
    assert t.occurrence == 1
    assert t.node_id == "/akn/au/act/1988/119#term-personal_information"


def test_defined_term_node_id_second_occurrence_suffixed():
    """occurrence=2 appends a __2 suffix, keeping the two nodes distinct."""
    t = DefinedTermNode(
        term="exempt income",
        display_term="exempt income",
        act_frbr_uri="/akn/au/act/1936/27",
        section_eid="part-III__sec-23",
        definition_text="income derived from a source outside Australia by a person who is a resident",
        occurrence=2,
    )
    assert t.node_id == "/akn/au/act/1936/27#term-exempt_income__2"


def test_defined_term_node_id_third_occurrence_suffixed():
    t = DefinedTermNode(
        term="exempt income",
        display_term="exempt income",
        act_frbr_uri="/akn/au/act/1936/27",
        section_eid="part-III__sec-23",
        definition_text="a pension, allowance or benefit specified in Schedule 5",
        occurrence=3,
    )
    assert t.node_id == "/akn/au/act/1936/27#term-exempt_income__3"
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_models.py -k occurrence -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'occurrence'`

### Step 3: Write the implementation

In `src/lexaugraph/models.py`, replace the `DefinedTermNode` class (lines 26-36):

```python
@dataclass
class DefinedTermNode:
    term: str
    display_term: str
    act_frbr_uri: str
    section_eid: str
    definition_text: str
    occurrence: int = 1

    @property
    def node_id(self) -> str:
        slug = self.term.replace(" ", "_").replace("-", "_")
        base = f"{self.act_frbr_uri}#term-{slug}"
        if self.occurrence > 1:
            return f"{base}__{self.occurrence}"
        return base
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_models.py -k occurrence -v`
Expected: PASS (3 tests)

### Step 5: Run full suite, then commit

Run: `python -m pytest -q`
Expected: all existing tests still pass (no regressions — `occurrence` defaults to 1, which is a no-op for every existing test's node_id assertions), plus 3 new.

```bash
git add src/lexaugraph/models.py tests/test_models.py
git commit -m "feat: add occurrence field to DefinedTermNode.node_id"
```

---

## Task 2: Wire occurrence counting into `_add_act_nodes`

**Files:**
- Modify: `src/lexaugraph/graph.py:40-79` (`_add_act_nodes`)
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: `DefinedTermNode.occurrence` (Task 1).
- Produces: `_add_act_nodes` now mutates `term.occurrence` on each `DefinedTermNode` in `act_data.defined_terms` as a side effect of iteration, before calling `add_node`. No new public function — the fix is entirely inside the existing method.

### Step 1: Write the failing test

Add to `tests/test_graph.py`, after `test_defines_edges` (after line 65):

```python
def test_multi_meaning_terms_survive_as_distinct_nodes():
    """Same-Act, same-slug terms with genuinely different definition_text
    (real OPC drafting -- e.g. ITAA 1936's 'exempt income' has 4 distinct
    meanings) must NOT silently overwrite each other in the graph. Confirmed
    bug before this fix: add_node's second call with the same node_id
    overwrites the first's attributes, and the first node is gone."""
    act = ActNode(frbr_uri="/akn/au/act/1936/27", title="Income Tax Assessment Act 1936", year=1936)
    section = SectionNode(
        eid="part-III__sec-23", act_frbr_uri="/akn/au/act/1936/27",
        heading="Exemptions", text="...",
    )
    term_a = DefinedTermNode(
        term="exempt income", display_term="exempt income",
        act_frbr_uri="/akn/au/act/1936/27", section_eid="part-III__sec-23",
        definition_text="income derived from a source outside Australia by a resident",
    )
    term_b = DefinedTermNode(
        term="exempt income", display_term="exempt income",
        act_frbr_uri="/akn/au/act/1936/27", section_eid="part-III__sec-23",
        definition_text="a pension, allowance or benefit specified in Schedule 5",
    )
    data = ActData(act_node=act, sections=[section], defined_terms=[term_a, term_b], ref_edges=[])

    g = LexAuGraph()
    g.add_act_data(data)

    term_nodes = [
        n for n, d in g.graph.nodes(data=True)
        if d.get("type") == "defined_term" and d.get("term") == "exempt income"
    ]
    assert len(term_nodes) == 2

    def_texts = {g.graph.nodes[n]["definition_text"] for n in term_nodes}
    assert "income derived from a source outside Australia by a resident" in def_texts
    assert "a pension, allowance or benefit specified in Schedule 5" in def_texts

    # occurrence side effect is visible on the caller's objects
    assert term_a.occurrence == 1
    assert term_b.occurrence == 2
```

### Step 2: Run test to verify it fails

Run: `python -m pytest tests/test_graph.py -k multi_meaning -v`
Expected: FAIL — `assert len(term_nodes) == 2` fails with `1 == 2` (today's collision bug: `term_b` silently overwrites `term_a`'s node).

### Step 3: Write the implementation

In `src/lexaugraph/graph.py`, replace the defined-terms loop inside `_add_act_nodes` (currently lines 67-79):

```python
        term_occurrence_counts: dict[str, int] = {}
        for term in act_data.defined_terms:
            slug = term.term.replace(" ", "_").replace("-", "_")
            term_occurrence_counts[slug] = term_occurrence_counts.get(slug, 0) + 1
            term.occurrence = term_occurrence_counts[slug]
            self.graph.add_node(
                term.node_id,
                type="defined_term",
                term=term.term,
                display_term=term.display_term,
                act_frbr_uri=term.act_frbr_uri,
                section_eid=term.section_eid,
                definition_text=term.definition_text,
            )
            if term.section_eid:
                section_id = f"{term.act_frbr_uri}#{term.section_eid}"
                if section_id in self.graph.nodes:
                    self.graph.add_edge(section_id, term.node_id, type="defines")
```

### Step 4: Run test to verify it passes

Run: `python -m pytest tests/test_graph.py -k multi_meaning -v`
Expected: PASS

### Step 5: Run full suite, then commit

Run: `python -m pytest -q`
Expected: all existing tests pass (the counter starts fresh per `_add_act_nodes` call, and every existing single-occurrence fixture gets `occurrence=1` — identical `node_id` to before), plus 1 new.

```bash
git add src/lexaugraph/graph.py tests/test_graph.py
git commit -m "fix: disambiguate colliding term node_ids per Act"
```

---

## Task 3: `find_all_definitions` returns every surviving meaning

**Files:**
- Test: `tests/test_resolver.py` (no production code change expected — this task's job is to prove the claim in writing, not implement anything new)

**Interfaces:**
- Consumes: `DefinitionResolver.find_all_definitions` (existing, `resolver.py:57-78`), the fixed `_add_act_nodes` (Task 2).
- Produces: nothing new — a regression test proving `find_all_definitions` needs no code change once distinct nodes exist.

### Step 1: Write the test

Add to `tests/test_resolver.py`:

```python
def test_find_all_definitions_returns_every_meaning_after_node_id_fix():
    """find_all_definitions already iterates every matching graph node --
    once _add_act_nodes stops overwriting same-slug nodes (Task 2), this
    returns multiple DefinitionResults with no resolver code change."""
    from lexaugraph.models import ActNode, SectionNode, DefinedTermNode, ActData
    from lexaugraph.graph import LexAuGraph
    from lexaugraph.resolver import DefinitionResolver

    act = ActNode(frbr_uri="/akn/au/act/1936/27", title="Income Tax Assessment Act 1936", year=1936)
    section = SectionNode(
        eid="part-III__sec-23", act_frbr_uri="/akn/au/act/1936/27",
        heading="Exemptions", text="...",
    )
    term_a = DefinedTermNode(
        term="exempt income", display_term="exempt income",
        act_frbr_uri="/akn/au/act/1936/27", section_eid="part-III__sec-23",
        definition_text="income derived from a source outside Australia by a resident",
    )
    term_b = DefinedTermNode(
        term="exempt income", display_term="exempt income",
        act_frbr_uri="/akn/au/act/1936/27", section_eid="part-III__sec-23",
        definition_text="a pension, allowance or benefit specified in Schedule 5",
    )
    data = ActData(act_node=act, sections=[section], defined_terms=[term_a, term_b], ref_edges=[])

    g = LexAuGraph()
    g.add_act_data(data)
    resolver = DefinitionResolver(g)

    results = resolver.find_all_definitions("exempt income")
    assert len(results) == 2
    def_texts = {r.definition_text for r in results}
    assert "income derived from a source outside Australia by a resident" in def_texts
    assert "a pension, allowance or benefit specified in Schedule 5" in def_texts
```

### Step 2: Run test

Run: `python -m pytest tests/test_resolver.py -k find_all_definitions_returns_every_meaning -v`
Expected: PASS immediately (no implementation step needed — Task 2 already fixed the underlying cause).

### Step 3: Run full suite, then commit

Run: `python -m pytest -q`
Expected: all pass, plus 1 new.

```bash
git add tests/test_resolver.py
git commit -m "test: confirm find_all_definitions needs no change post-fix"
```

---

## Task 4: Rebuild against corrected corpus + verify the 746 known collision slugs

**Files:**
- Create: `scripts/verify_collisions.py`

**Interfaces:**
- Consumes: `lexaugraph build` (existing CLI), the `lex-au` corpus at `../lex-au/repo/corpus/xml/` (must already reflect the `list-definition-truncation` fix — see stop point below).
- Produces: a printed report — manual verification gate, not part of any build pipeline.

**Dependency:** this task requires `lex-au`'s `docs/superpowers/plans/2026-07-14-list-definition-truncation.md` Task 4 (corpus verification) to have passed, and its corpus rebuild to have actually run — otherwise this is measuring against the corpus's pre-fix state and Task 4's "already-fixed `<def>` content" checks below will fail for reasons unrelated to this plan's node_id fix. **Do not run this task until `lex-au`'s corpus rebuild is confirmed done.**

### Step 1: Write the verification script

Create `scripts/verify_collisions.py`:

```python
"""One-off verification: rebuild the graph from the (already-fixed) lex-au
corpus and confirm every previously-colliding term slug now survives as
multiple distinct nodes, queryable via find_all_definitions.
"""
from pathlib import Path
from lexaugraph.graph import LexAuGraph
from lexaugraph.resolver import DefinitionResolver

CORPUS_DIR = Path("../../lex-au/repo/corpus/")


def main() -> None:
    g = LexAuGraph()
    g.build(CORPUS_DIR)

    resolver = DefinitionResolver(g)

    slug_counts: dict[tuple[str, str], int] = {}
    for node_id, data in g.graph.nodes(data=True):
        if data.get("type") != "defined_term":
            continue
        key = (data.get("act_frbr_uri", ""), data.get("term", ""))
        slug_counts[key] = slug_counts.get(key, 0) + 1

    collisions = {k: v for k, v in slug_counts.items() if v > 1}
    print(f"Distinct (Act, term) pairs with 2+ surviving graph nodes: {len(collisions)}")
    print("(spec's independently-verified count: 746 distinct colliding slugs, pre-rebuild)")

    print()
    print("Spot-check: ITAA 1936 'exempt income' (spec-cited 4 distinct meanings)")
    results = resolver.find_all_definitions("exempt income")
    itaa_1936 = [r for r in results if r.act_frbr_uri == "/akn/au/act/1936/27"]
    print(f"  find_all_definitions('exempt income') for ITAA 1936: {len(itaa_1936)} results")
    for r in itaa_1936:
        print(f"    - {r.definition_text[:80]}...")


if __name__ == "__main__":
    main()
```

### Step 2: Run it and evaluate

Run: `python scripts/verify_collisions.py`

Expected: "Distinct (Act, term) pairs with 2+ surviving graph nodes" close to 746 (some drift acceptable — the spec's count was pre-rebuild static analysis, this is a live post-fix graph build). The ITAA 1936 "exempt income" spot-check should show multiple (spec cites 4) distinct definition texts, not 1.

If the count comes back **lower** than expected (e.g. under ~600), investigate before proceeding — it likely means the corpus rebuild dependency (see this task's header) hasn't actually landed, or `load_corpus`/`lexaugraph build` needs to be re-run against the current corpus state.

### Step 3: Commit the verification script

```bash
git add scripts/verify_collisions.py
git commit -m "test: add post-rebuild collision verification script"
```

**STOP POINT.** Do not run `lexaugraph build --corpus-dir ../lex-au/repo/corpus/` to overwrite the committed `graph.json` artifact, or redeploy any consumer, without explicit user go-ahead. Report the verification script's output and stop here.
