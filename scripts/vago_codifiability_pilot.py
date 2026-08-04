"""One-off pilot: does VAGO's English vagueness score agree with ClauseKit's
hand-labelled codifiability tag?

Gates item #4 of the 2026-07-31 six-item scoping session (codifiability/complexity
scoring) per the open risk flagged in
docs/2026-07-22-codifiability-scoring-research.md: VAGO's English variant is a
neural clone trained on French press text (FreSaDa), with no legal-domain or
Australian-English validation. Cheap check before committing engineering time --
run it against 10-20 already hand-labelled EU AI Act/NDB rules (ClauseKit) and
eyeball agreement, rather than trust the transfer.

No public pip package or importable model exists for VAGO -- it's a hosted research
demo (Institut Jean-Nicod / Mondeca, DIEKB project). This script calls the same
CAM workflow API the demo's own "Test it" button calls
(https://research.mondeca.com/demo/vago/), found via browser network inspection --
undocumented but public, no auth required. Kept to a small, one-off sample size
out of courtesy to a third-party research endpoint; not a pattern to scale into a
production pipeline without asking Mondeca first.
"""
import json
import random
import time
from pathlib import Path

import requests

CLAUSE_KIT_RULES = Path("../../clause-kit/repo/rules")
VAGO_RUN_URL = "https://research.mondeca.com/cam/ca-ws/rs/process/run"
VAGO_STATUS_URL = "https://research.mondeca.com/cam/ca-ws/rs/process/{id}/status"
VAGO_RESULTS_URL = (
    "https://research.mondeca.com/cam/ca-ws/rs/process/{id}/results/validMetadata"
)
WORKFLOW = "workflows/DIEKB_vagueness_spacy_en.xml"
SAMPLE_PER_LABEL = 5
POLL_DELAY_SECONDS = 0.5
REQUEST_GAP_SECONDS = 1.0  # be a polite guest of a third-party research demo


def sample_rules() -> list[dict]:
    random.seed(42)
    with open(CLAUSE_KIT_RULES / "eu-ai-act.json") as f:
        eu = json.load(f)["rules"]
    with open(CLAUSE_KIT_RULES / "ndb.json") as f:
        ndb = json.load(f)["rules"]

    by_label: dict[str, list[dict]] = {}
    for r in eu:
        by_label.setdefault(r["codifiability"], []).append(r)

    sample = []
    for label in ["low", "medium", "high"]:
        pool = by_label.get(label, [])
        random.shuffle(pool)
        sample.extend(pool[:SAMPLE_PER_LABEL])

    ndb_low = [r for r in ndb if r["codifiability"] == "low"]
    random.shuffle(ndb_low)
    sample.extend(ndb_low[:SAMPLE_PER_LABEL])
    return sample


def score_text(text: str, urn: str) -> dict:
    resp = requests.post(
        VAGO_RUN_URL,
        json={
            "name": WORKFLOW,
            "document": {"content": text, "uri": urn},
            "block_request": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    process_id = resp.json()["processId"]

    while True:
        status_resp = requests.get(VAGO_STATUS_URL.format(id=process_id), timeout=30)
        status_resp.raise_for_status()
        if status_resp.json()["process_status"] == "DONE":
            break
        time.sleep(POLL_DELAY_SECONDS)

    results_resp = requests.get(VAGO_RESULTS_URL.format(id=process_id), timeout=30)
    results_resp.raise_for_status()
    return results_resp.json()["document"]


def main() -> None:
    rules = sample_rules()
    rows = []
    for i, rule in enumerate(rules):
        doc = score_text(rule["obligation"], urn=f"urn:pilot:{i}")
        row = {
            "rule_id": rule["rule_id"],
            "codifiability": rule["codifiability"],
            "meanRatioVague": float(doc["meanRatioVague"]),
            "meanRatioPrecis": float(doc["meanRatioPrecis"]),
            "meanRatioOpinion": float(doc["meanRatioOpinion"]),
            "vagueSentences": int(doc["vagueSentencesCounter"]),
            "totalSentences": int(doc["totalSentencesCounter"]),
        }
        rows.append(row)
        print(f"{rule['rule_id']:45s} {rule['codifiability']:8s} "
              f"vague={row['meanRatioVague']:.3f} precis={row['meanRatioPrecis']:.3f}")
        time.sleep(REQUEST_GAP_SECONDS)

    print()
    print("Mean VAGO vagueness ratio by codifiability label:")
    for label in ["low", "medium", "high"]:
        vals = [r["meanRatioVague"] for r in rows if r["codifiability"] == label]
        if vals:
            print(f"  {label:8s} n={len(vals):2d}  mean_vague={sum(vals)/len(vals):.3f}")

    out_path = Path("vago_pilot_results.json")
    out_path.write_text(json.dumps(rows, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
