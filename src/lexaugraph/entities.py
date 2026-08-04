from __future__ import annotations
import re
from typing import Optional

OFFICE_KEYWORDS = {
    "secretary", "commissioner", "minister", "tribunal", "registrar",
    "agency", "authority", "regulator", "ombudsman", "department", "court",
}


def classify_entity_type(display_term: str) -> Optional[str]:
    """Classify a defined term's display text as an office/agency entity type.

    Closed-lexicon whole-word match (not substring) -- e.g. "Regulatory Powers
    Act" must NOT match "regulator" or "department" via a fragment. If more
    than one keyword matches (e.g. a term containing both "Department" and
    "Authority"), the longest/most specific keyword wins. Returns None for
    ordinary (non-entity) defined terms.
    """
    words = re.findall(r"[A-Za-z]+", display_term.lower())
    matches = [kw for kw in OFFICE_KEYWORDS if kw in words]
    if not matches:
        return None
    return max(matches, key=len)
