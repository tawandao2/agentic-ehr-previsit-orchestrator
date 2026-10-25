"""Deterministic diabetes care-gap rules.

These rules are the ground truth for the project. The LLM agent never decides
whether a gap exists; it only explains gaps found here, and its output is later
scored against this file.

Definitions are adapted from published quality measures and simplified:
  * HbA1c poor control  - CMS122 (most recent HbA1c > 9.0%)
  * Retinal eye exam    - CMS131 (simplified: exam within the lookback window)
  * Kidney evaluation   - HEDIS KED (needs both eGFR and uACR)
  * HbA1c above goal    - NOT a CMS measure. 7.0% is a common general target,
                          but real targets are individualised by the clinician.
Deviations: rolling 12-month lookback from the visit date instead of the
calendar measurement year (better for pre-visit use); hospice/frailty/palliative
exclusions other than hospice are not modelled.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

T2DM = "44054006"
HBA1C, EGFR, UACR = "4548-4", "33914-3", "14959-1"
EYE_EXAM = "722161008"
HOSPICE = {"385763009", "876882001"}
LOOKBACK_DAYS = 365


@dataclass
class Gap:
    patient_id: str
    gap_type: str
    detail: str
    evidence_ids: list = field(default_factory=list)  # FHIR resource ids behind the finding


def _d(s):
    return date.fromisoformat(s[:10])


def _recent(rows, as_of):
    """Rows (dicts with 'date') inside the lookback window, newest first."""
    lo = as_of - timedelta(days=LOOKBACK_DAYS)
    return sorted([r for r in rows if lo < _d(r["date"]) <= as_of],
                  key=lambda r: r["date"], reverse=True)


def evaluate_patient(chart: dict, as_of: date):
    """chart = {patient_id, birth_date, conditions:[{id,code,status}],
    hba1c:[{id,date,value}], egfr:[...], uacr:[...], eye_exams:[{id,date}]}
    Returns (eligible, reason, gaps)."""
    pid = chart["patient_id"]
    if not any(c["code"] == T2DM and c["status"] == "active" for c in chart["conditions"]):
        return False, "no active type 2 diabetes", []
    if any(c["code"] in HOSPICE for c in chart["conditions"]):
        return False, "hospice exclusion", []

    age = (as_of - _d(chart["birth_date"])).days // 365.25
    gaps = []

    a1c = _recent(chart["hba1c"], as_of)
    if not a1c:
        last = sorted(chart["hba1c"], key=lambda r: r["date"], reverse=True)[:1]
        gaps.append(Gap(pid, "HBA1C_OVERDUE", "No HbA1c in the last 12 months"
                        + (f" (last on {last[0]['date']})" if last else " (none on record)"),
                        [r["id"] for r in last]))
    else:
        v = float(a1c[0]["value"])
        if v > 9.0:
            gaps.append(Gap(pid, "HBA1C_POOR_CONTROL",
                            f"Most recent HbA1c {v}% on {a1c[0]['date']} (above 9.0%)", [a1c[0]["id"]]))
        elif v >= 7.0:
            gaps.append(Gap(pid, "HBA1C_ABOVE_GOAL",
                            f"Most recent HbA1c {v}% on {a1c[0]['date']} (at or above 7.0%)", [a1c[0]["id"]]))

    if not _recent(chart["eye_exams"], as_of):
        last = sorted(chart["eye_exams"], key=lambda r: r["date"], reverse=True)[:1]
        gaps.append(Gap(pid, "EYE_EXAM_DUE", "No diabetic retinal eye exam in the last 12 months"
                        + (f" (last on {last[0]['date']})" if last else " (none on record)"),
                        [r["id"] for r in last]))

    e, u = _recent(chart["egfr"], as_of), _recent(chart["uacr"], as_of)
    if not (e and u):
        missing = " and ".join(n for n, x in (("eGFR", e), ("uACR", u)) if not x)
        gaps.append(Gap(pid, "KIDNEY_EVAL_DUE", f"No {missing} in the last 12 months",
                        [x[0]["id"] for x in (e, u) if x]))
    return True, f"age {int(age)}", gaps
