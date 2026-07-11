#!/usr/bin/env python3
"""Reconcile lex-au-graph citation_candidates.json against legislation.gov.au.

Bridges `lexaugraph build`'s citation_candidates.json output to lex-au's
`lexau build --list-file`: takes the raw candidate list (often
truncated/duplicate/renamed titles -- see the extraction-artifact notes
below) and resolves each to a confirmed, currently in-force, non-duplicate
official title, ready to feed straight into ingestion.

Usage:
    python reconcile_candidates.py <citation_candidates.json> <acts.txt> \\
        [threshold=5] [top_n=50] [out=reconcile_report.json]

    # then split the report's top_n_selected by doc_type and run:
    #   lexau build --list-file <acts.txt> --type act
    #   lexau build --list-file <regs.txt> --type regulation

For each candidate (mention_count >= threshold), determines one of:
  - DUPLICATE: substring of an Act/Reg already in the corpus (title-matching
    artifact in lex-au-graph's citation extraction -- comma/apostrophe/paren
    handling), or a historical name for something already in the corpus
    (renamed Act, see RENAMED_TO_EXISTING below).
  - GENUINE: resolves to a real, currently in-force, not-yet-in-corpus
    title via a `contains()` OData search against
    api.prod.legislation.gov.au.
  - NON_CURRENT: no in-force title found at all.
  - AMBIGUOUS: multiple non-amendment principal titles matched the same
    fragment -- not auto-resolved, needs a human.
  - UNRESOLVED: some Act/Reg hits found but none confirmed by suffix match
    -- needs a human to reconstruct the real title (or is legitimately a
    correctly-excluded "X Amendment Act" title, see AMENDMENT_RE).
  - KNOWN_UNFETCHABLE: resolves fine, but legislation.gov.au only has a
    legacy .doc/RTF compilation on file -- lex-au's builder can't parse it
    (source-data gap, not a bug). Hardcoded list built up across corpus-
    expansion rounds; extend it when a new title fails ingestion the same
    way (see lex-au-graph/docs/citation-candidate-ambiguity-log.md at the
    project wrapper level for the full incident history).
  - RENAMED_TO_EXISTING: candidate is a historical name for an Act already
    in the corpus under a different current name (e.g. "Trade Practices
    Act 1974" -> "Competition and Consumer Act 2010"). Resolved via
    build_rename_map() against each existing Act's `nameHistory`.

Caches API-lookup results (reconcile_cache.json) and the rename map
(rename_map_cache.json) alongside this script -- both are safe to delete to
force fresh lookups (a cached "non_current" result could theoretically go
stale if the Act later commences), and both grow incrementally rather than
rebuilding from scratch on each run.

Writes a JSON report and a plain acts-to-add list (top N genuine, by
mention_count).
"""
import json
import os
import re
import sys
import time
import requests

API_BASE = "https://api.prod.legislation.gov.au/v1"
CANDIDATES_PATH = sys.argv[1]
ACTS_TXT_PATH = sys.argv[2]
THRESHOLD = int(sys.argv[3]) if len(sys.argv) > 3 else 5
TOP_N = int(sys.argv[4]) if len(sys.argv) > 4 else 50
OUT_PATH = sys.argv[5] if len(sys.argv) > 5 else "reconcile_report.json"

# Titles not yet in the corpus keep resurfacing as candidates round after
# round (they're only removed from citation_candidates.json once actually
# ingested). Without a cache, every round re-queries the API from scratch
# for the same "unresolved"/"non_current" titles it already looked up last
# time. Cache resolution results by lowercased candidate title so repeat
# rounds skip the API call entirely for anything already resolved. A result
# could theoretically go stale (an Act commences after being seen as
# non_current), but that's rare over the days/weeks this loop runs across --
# delete the cache file to force a fresh check if that's ever suspected.
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconcile_cache.json")

session = requests.Session()
session.headers.update({"Accept": "application/json"})

AMENDMENT_RE = re.compile(r"\bAmendment\b|\bRepeal\b", re.I)
_TITLE_ID_RE = re.compile(r"C\d{4}A(\d+)")
_REG_RE = re.compile(r"C\d{4}R(\d+)")
# Modern legislative instruments (incl. Regulations/Rules made under the
# post-2016 framework) get F-prefixed ids, not the legacy C{year}R pattern --
# confirmed against lex-au's own corpus (Therapeutic Goods (Medical Devices)
# Regulations 2002 = F2002B00237, Superannuation Industry (Supervision)
# Regulations 1994 = F1996B00580). Only treat an F-prefixed hit as a
# *principal* Regulations/Rules title (not a notice/declaration referencing
# one) if the name itself ends cleanly in "Regulations/Rules <year>".
_F_PREFIX_RE = re.compile(r"^F\d{4}")
_CLEAN_REG_TITLE_RE = re.compile(r"\((?:Regulations?|Rules)\)?\s*\d{4}$|(?:Regulations?|Rules)\s*\d{4}$", re.I)

# Confirmed permanently un-fetchable: legislation.gov.au only has a legacy
# binary .doc (OLE2/CFB) or RTF compilation on file, not OOXML .docx -- lex-au's
# builder correctly rejects these (not a parser bug, a source-data gap; see
# lex-au-graph/docs/citation-candidate-ambiguity-log.md rounds 1-4). Since these
# Acts never get added to the corpus, they keep resurfacing as citation
# candidates every round -- exclude them here so a batch's TOP_N slots go to
# resolvable titles instead of guaranteed repeats.
KNOWN_UNFETCHABLE = {
    "statute law revision act 1996", "statute law revision act 2011",
    "statute law revision act 2010", "statute law revision act 2008",
    "corporations (repeals, consequentials and transitionals) act 2001",
    "fair work (state referral and consequential and other amendments) act 2009",
    "same-sex relationships (equal treatment in commonwealth laws—general law reform) act 2008",
    "financial services reform (consequential provisions) act 2001",
    "australian charities and not-for-profits commission (consequential and transitional) act 2012",
    "financial sector reform (consequential amendments) act 1998",
    "australian crime commission establishment act 2002",
    "a.c.t. self-government (consequential provisions) act 1988",
    "corporate law economic reform program act 1999",
    "superannuation legislation (consequential amendments and transitional provisions) act 2011",
    "corporate law economic reform program (audit reform and corporate disclosure) act 2004",
    "proceeds of crime (consequential amendments and transitional provisions) act 2002",
    "crimes legislation enhancement act 2003",
    "marine insurance act 1909",
    "financial services reform act 2001",
    "a new tax system (tax administration) act 1999",
    "personal liability for corporate fault reform act 2012",
    "law enforcement integrity commissioner (consequential amendments) act 2006",
    "statute law revision act 2006",
    "statute law revision act 2007",
    "income tax (consequential amendments) act 1997",
    "anti-terrorism act 2005",
    "death penalty abolition act 1973",
    "euthanasia laws act 1997",
    "flags act 1953",
    "statute of westminster adoption act 1942",
    "personal property securities (consequential amendments) act 2009",
    "tax law improvement act 1997",
    "financial sector reform (amendments and transitional provisions) act 1998",
    "abolition of compulsory age retirement (statutory officeholders) act 2001",
    "offshore petroleum (repeals and consequential amendments) act 2006",
    "special prosecutors act 1982",
    "work health and safety (transitional and consequential provisions) act 2011",
    "federal magistrates (consequential amendments) act 1999",
    "statute law revision act 2005",
    "law enforcement (afp professional standards and related measures) act 2006",
    "financial sector (collection of data—consequential and transitional provisions) act 2001",
    "new business tax system (capital allowances—transitional and consequential) act 2001",
    "new business tax system (franking deficit tax) act 2002",
    "tax agent services (transitional provisions and consequential amendments) act 2009",
    "designs (consequential amendments) act 2003",
    "navigation (consequential amendments) act 2012",
    "environmental reform (consequential provisions) act 1999",
    "first home saver accounts (consequential amendments) act 2008",
    "a new tax system (pay as you go) act 1999",
    "dental benefits (consequential amendments) act 2008",
    "superannuation benefits (supervisory mechanisms) act 1990",
    "superannuation contributions tax imposition act 1997",
    "australian passports (application fees) act 2005",
    "international criminal court (consequential amendments) act 2002",
    "industrial relations (consequential provisions) act 1988",
    "statute stocktake (regulatory and other laws) act 2009",
    "youth allowance consolidation act 2000",
    "petroleum resource rent tax (imposition—general) act 2012",
    "new business tax system (consolidation and other measures) act 2003",
    "superannuation (government co-contribution for low income earners) (consequential amendments) act 2003",
    "coastal waters (state powers) act 1980",
    "removal of prisoners (territories) act 1923",
    "environment protection (northern territory supreme court) act 1978",
    "midwife professional indemnity (run-off cover support payment) act 2010",
    "coastal waters (northern territory powers) act 1980",
    "territories law reform act 2010",
    "higher education support (transitional provisions and consequential amendments) act 2003",
    "us free trade agreement implementation act 2004",
    "cybercrime act 2001",
    "suppression of the financing of terrorism act 2002",
    "anti-money laundering and counter-terrorism financing (transitional provisions and consequential amendments) act 2006",
    "medical indemnity (consequential amendments) act 2002",
    "new business tax system (alienation of personal services income) act 2000",
    "new business tax system (capital allowances) act 2001",
    "new international tax arrangements (foreign-owned branches and other measures) act 2005",
    "superannuation (consequential amendments) act 2005",
    "gene technology (consequential amendments) act 2000",
    "circuit layouts act 1989",
    "a new tax system (goods and services tax imposition (recipients)—customs) act 2005",
    "petroleum (timor sea treaty) (consequential amendments) act 2003",
    "general insurance reform act 2001",
    "parliamentary precincts act 1988",
    "parliamentary papers act 1908",
    "carbon credits (consequential amendments) act 2011",
    "transport safety investigation (consequential amendments) act 2003",
    "carer recognition act 2010",
    "international trade integrity act 2007",
    "defence legislation (miscellaneous amendments) act 2009",
    "anti-people smuggling and other measures act 2010",
    "commonwealth functions (statutes review) act 1981",
    "personally controlled electronic health records (consequential amendments) act 2012",
    "new business tax system (capital gains tax) act 1999",
    "new business tax system (over-franking tax) act 2002",
    "taxation laws (technical amendments) act 1998",
    "new business tax system (debt and equity) act 2001",
    "new business tax system (imputation) act 2002",
    "nation-building funds (consequential amendments) act 2008",
    "clean energy (household assistance amendments) act 2011",
}


def api_get(path, params, _retries=3):
    """GET with a short retry for transient connection failures.

    Round 9 crashed the whole script (1123-candidate run) on an unhandled
    requests.ConnectionError ("Remote end closed connection without
    response") -- a network blip, not a bad query. HTTPError (4xx/5xx from
    raise_for_status) is a real per-query signal and propagates immediately
    for resolve_candidate's existing handling; only connection/timeout-level
    failures get retried here.
    """
    for attempt in range(_retries):
        try:
            r = session.get(f"{API_BASE}/{path}", params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError:
            raise
        except requests.exceptions.RequestException:
            if attempt == _retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def search_contains(fragment, top=15):
    frag = fragment.replace("'", "''")
    resp = api_get(
        "Titles",
        {
            "$filter": f"contains(name,'{frag}') and isInForce eq true",
            "$select": "id,name",
            "$top": top,
        },
    )
    return resp.get("value", [])


RENAME_MAP_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rename_map_cache.json")


def build_rename_map(existing_acts):
    """Precompute {historical_name_lowercase: current_name} for every Act
    already in the corpus, e.g. "trade practices act 1974" ->
    "Competition and Consumer Act 2010".

    OData's `contains(name, ...)` only searches a title's *current* name --
    an old name like "Trade Practices Act 1974" can't be found that way
    since the record's name field is now "Competition and Consumer Act
    2010". And nameHistory isn't filterable server-side (confirmed live
    2026-07-11: `nameHistory/any(...)` 400s with an internal LINQ error, not
    a clean "unsupported" response). So this fetches each existing Act's
    full record once (nameHistory comes back by default, unselected) and
    builds the reverse map locally -- a one-time cost, cached to disk and
    only extended for acts.txt entries not already in the cache.
    """
    cache = json.load(open(RENAME_MAP_CACHE_PATH)) if os.path.exists(RENAME_MAP_CACHE_PATH) else {}
    known_acts = set(cache.get("_acts_covered", []))
    rename_map = {k: v for k, v in cache.items() if k != "_acts_covered"}

    new_acts = [a for a in existing_acts if a not in known_acts]
    for i, act_name in enumerate(new_acts):
        try:
            resp = api_get("Titles", {"$filter": f"name eq '{act_name}'", "$top": 1})
        except requests.exceptions.RequestException:
            continue
        records = resp.get("value", [])
        if not records:
            continue
        for h in records[0].get("nameHistory") or []:
            hn = h.get("name", "").lower()
            if hn and hn != act_name.lower():
                rename_map[hn] = act_name
        known_acts.add(act_name)
        if i % 20 == 0:
            time.sleep(0.3)

    cache_out = dict(rename_map)
    cache_out["_acts_covered"] = sorted(known_acts)
    json.dump(cache_out, open(RENAME_MAP_CACHE_PATH, "w"), indent=2)
    return rename_map


def best_keyword_fragment(title):
    # Strip trailing year, drop leading connector words already excluded by
    # the extractor (of/and), pick the longest capitalizable stretch.
    t = re.sub(r"\s+\d{4}$", "", title).strip()
    # If it starts with a stray closing paren fragment, drop leading junk up
    # to the first letter run that looks like a real word start.
    t = t.lstrip(") ").strip()
    return t


def resolve_candidate(title):
    """Try to resolve a possibly-truncated candidate title to an in-force Act/Reg.

    Returns (status, resolved_name_or_None, title_id_or_None)
    status in {"genuine", "non_current", "ambiguous", "unresolved"}
    """
    frag = best_keyword_fragment(title)
    tried = set()
    any_principal_hits = False
    for attempt_frag in _fragment_variants(frag):
        if attempt_frag in tried or len(attempt_frag) < 6:
            continue
        tried.add(attempt_frag)
        try:
            results = search_contains(attempt_frag)
        except requests.exceptions.RequestException:
            # HTTPError (bad query) or a connection failure that survived
            # api_get's retries -- either way, try the next fragment rather
            # than losing the whole run for one candidate.
            continue
        # Restrict to real Act/Regulation title records: legacy C{year}A
        # (Act) / C{year}R (Regulations) ids, or an F-prefixed instrument id
        # whose name is itself a clean "... Regulations/Rules <year>" title
        # (not a notice/declaration that merely references one).
        principal_only = [
            r for r in results
            if _TITLE_ID_RE.match(r["id"]) or _REG_RE.match(r["id"])
            or (_F_PREFIX_RE.match(r["id"]) and _CLEAN_REG_TITLE_RE.search(r["name"]))
        ]
        if principal_only:
            any_principal_hits = True
        # Prefer results that are not amendment/repeal acts and whose name,
        # lowercased, ends with the candidate title (candidate is a suffix
        # of the real title -- confirms truncation direction).
        candidates_ok = [
            r for r in principal_only
            if not AMENDMENT_RE.search(r["name"])
            and r["name"].lower().rstrip().endswith(title.lower().rstrip())
        ]
        if len(candidates_ok) == 1:
            return "genuine", candidates_ok[0]["name"], candidates_ok[0]["id"]
        if len(candidates_ok) > 1:
            # multiple non-amendment matches ending in the candidate title -- ambiguous
            return "ambiguous", [r["name"] for r in candidates_ok], None
        # No suffix-confirmed match from this fragment. Do NOT fall back to
        # "the only non-amendment principal-title hit" -- that produced false
        # matches (e.g. "corporations regulations 2001" -> unrelated
        # "Ordinances and Regulations (Notification) Act 1978", because a
        # short/generic search fragment coincidentally matched via contains()
        # on an unrelated title). Keep trying other fragment variants instead.
    if any_principal_hits:
        # Got some principal Act/Reg hits at some point but none confirmed by
        # suffix match -- needs a human to eyeball the real title, don't guess.
        return "unresolved", None, None
    return "non_current", None, None


def _fragment_variants(frag):
    words = frag.split()
    yield frag
    # progressively drop leading word (handles missing leading qualifier words
    # the regex extractor chopped off)
    for i in range(1, min(3, len(words))):
        yield " ".join(words[i:])
    # also try dropping a trailing parenthetical if present, to search on the
    # core phrase only
    core = re.sub(r"\([^)]*\)", "", frag).strip()
    if core and core != frag:
        yield core


def main():
    candidates = json.load(open(CANDIDATES_PATH))
    candidates = [c for c in candidates if c["mention_count"] >= THRESHOLD]
    candidates.sort(key=lambda c: -c["mention_count"])

    existing = [l.strip() for l in open(ACTS_TXT_PATH) if l.strip()]
    existing_lower = [e.lower() for e in existing]

    print(f"Building/updating rename map for {len(existing)} existing corpus Acts...")
    rename_map = build_rename_map(existing)
    print(f"Rename map has {len(rename_map)} historical-name entries.")

    cache = json.load(open(CACHE_PATH)) if os.path.exists(CACHE_PATH) else {}
    cache_hits = 0
    renamed_hits = 0

    report = {"duplicate": [], "genuine": [], "non_current": [], "ambiguous": [], "unresolved": [], "known_unfetchable": [], "renamed_to_existing": []}
    genuine_accepted = []

    for c in candidates:
        title = c["title"]
        mc = c["mention_count"]

        # duplicate check: candidate title is a substring of an existing act/reg
        dup_match = next((e for e in existing_lower if title in e), None)
        if dup_match:
            report["duplicate"].append({"mention_count": mc, "title": title, "matched_existing": dup_match})
            continue

        # renamed-Act check: candidate is a historical name for something
        # already in the corpus under its current name (e.g. "trade
        # practices act 1974" -> "Competition and Consumer Act 2010").
        # Free (no API call) once the rename map is built.
        if title in rename_map:
            renamed_hits += 1
            report["renamed_to_existing"].append(
                {"mention_count": mc, "title": title, "current_name": rename_map[title]}
            )
            continue

        if title in cache:
            status, resolved, title_id = cache[title]
            cache_hits += 1
        else:
            status, resolved, title_id = resolve_candidate(title)
            cache[title] = [status, resolved, title_id]
            time.sleep(0.3)
            # Checkpoint every 20 newly-resolved candidates so a crash
            # partway through a large run (round 9 lost 1123 candidates'
            # worth of work to one unhandled ConnectionError) doesn't throw
            # away everything done so far -- a rerun after a crash will
            # cache-hit through all of this instead of re-querying.
            if len(cache) % 20 == 0:
                json.dump(cache, open(CACHE_PATH, "w"), indent=2)

        if status == "genuine":
            resolved_lower = resolved.lower()
            if resolved_lower in existing_lower:
                report["duplicate"].append({"mention_count": mc, "title": title, "matched_existing": resolved})
                continue
            if resolved_lower in KNOWN_UNFETCHABLE:
                report["known_unfetchable"].append({"mention_count": mc, "title": title, "resolved_name": resolved})
                continue
            doc_type = "regulation" if _CLEAN_REG_TITLE_RE.search(resolved) else "act"
            entry = {
                "mention_count": mc, "title": title, "resolved_name": resolved,
                "title_id": title_id, "doc_type": doc_type,
            }
            report["genuine"].append(entry)
            if len(genuine_accepted) < TOP_N:
                genuine_accepted.append(entry)
        elif status == "ambiguous":
            report["ambiguous"].append({"mention_count": mc, "title": title, "candidates": resolved})
        elif status == "unresolved":
            report["unresolved"].append({"mention_count": mc, "title": title})
        else:
            report["non_current"].append({"mention_count": mc, "title": title})

        print(f"{mc:>4} | {status:>11} | {title} -> {resolved if status=='genuine' else ''}", flush=True)

    report["top_n_selected"] = genuine_accepted
    json.dump(report, open(OUT_PATH, "w"), indent=2)
    json.dump(cache, open(CACHE_PATH, "w"), indent=2)
    print(f"\nWrote {OUT_PATH}")
    print(f"genuine={len(report['genuine'])} duplicate={len(report['duplicate'])} "
          f"non_current={len(report['non_current'])} ambiguous={len(report['ambiguous'])} "
          f"unresolved={len(report['unresolved'])} known_unfetchable={len(report['known_unfetchable'])} "
          f"renamed_to_existing={renamed_hits}")
    print(f"Selected top {len(genuine_accepted)} for this round.")
    print(f"Cache hits: {cache_hits} (skipped API calls); cache now has {len(cache)} entries -> {CACHE_PATH}")


if __name__ == "__main__":
    main()
