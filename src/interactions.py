"""Drug-drug interaction check on a patient's ACTIVE medications.

Ingredient matching is done on whole words in the RxNorm display text, so a
combination product (e.g. hydrochlorothiazide / lisinopril) matches every
ingredient it contains. The interaction table is pluggable:
  * data/interactions_seed.csv  - small author-curated demo set (FDA labeling)
  * DDInter CSV exports         - load with load_ddinter(); NOT bundled in the
    repo because DDInter is CC BY-NC-SA 4.0 (download it yourself, cite it).
"""
import csv, glob, re
from dataclasses import dataclass


@dataclass
class Alert:
    patient_id: str
    severity: str
    ingredient_a: str
    ingredient_b: str
    med_ids: list      # the two MedicationRequest resource ids
    note: str
    source: str


def load_seed(path):
    return [{"a": r["drug_a"].lower(), "b": r["drug_b"].lower(), "severity": r["severity"],
             "note": r["note"], "source": r["source"]} for r in csv.DictReader(open(path))]


def load_ddinter(folder):
    """Reads DDInter's per-ATC download CSVs (columns assumed: Drug_A, Drug_B, Level).
    Check the headers against the files you download."""
    out, seen = [], set()
    for f in glob.glob(f"{folder}/*.csv"):
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            a, b, lvl = r["Drug_A"].lower(), r["Drug_B"].lower(), r["Level"]
            if (a, b) in seen or (b, a) in seen: continue
            seen.add((a, b))
            out.append({"a": a, "b": b, "severity": lvl, "note": "", "source": "DDInter"})
    return out


def ingredients_in(display, vocabulary):
    text = display.lower()
    return {w for w in vocabulary if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text)}


def check_patient(patient_id, meds, table):
    """meds = [{id, display, status}]. Only active orders are checked."""
    vocab = {r["a"] for r in table} | {r["b"] for r in table}
    active = [(m["id"], ingredients_in(m["display"], vocab)) for m in meds if m["status"] == "active"]
    alerts, done = [], set()
    for r in table:
        a_ids = [i for i, ing in active if r["a"] in ing]
        b_ids = [i for i, ing in active if r["b"] in ing]
        for ia in a_ids:
            for ib in b_ids:
                if ia == ib: continue          # same product contains both: not an interaction between orders
                key = (frozenset((ia, ib)), frozenset((r["a"], r["b"])))
                if key in done: continue
                done.add(key)
                alerts.append(Alert(patient_id, r["severity"], r["a"], r["b"], [ia, ib], r["note"], r["source"]))
    return alerts
