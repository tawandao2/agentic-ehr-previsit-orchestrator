import sys, pathlib
from datetime import date
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
from care_gaps import evaluate_patient

AS_OF = date(2026, 10, 25)

def chart(**kw):
    base = {"patient_id": "p1", "birth_date": "1970-01-01",
            "conditions": [{"id": "c1", "code": "44054006", "status": "active"}],
            "hba1c": [], "egfr": [], "uacr": [], "eye_exams": []}
    base.update(kw)
    return base

def types(c):
    ok, _, gaps = evaluate_patient(c, AS_OF)
    return ok, {g.gap_type for g in gaps}

def test_not_diabetic_is_not_evaluated():
    ok, t = types(chart(conditions=[]))
    assert not ok and t == set()

def test_hospice_is_excluded():
    ok, _ = types(chart(conditions=[{"id": "c1", "code": "44054006", "status": "active"},
                                    {"id": "c2", "code": "385763009", "status": "active"}]))
    assert not ok

def test_no_data_flags_everything_due():
    _, t = types(chart())
    assert t == {"HBA1C_OVERDUE", "EYE_EXAM_DUE", "KIDNEY_EVAL_DUE"}

def test_poor_control_over_9():
    _, t = types(chart(hba1c=[{"id": "a", "date": "2026-09-01", "value": "9.4"}]))
    assert "HBA1C_POOR_CONTROL" in t and "HBA1C_ABOVE_GOAL" not in t

def test_exactly_9_is_not_poor_control():
    _, t = types(chart(hba1c=[{"id": "a", "date": "2026-09-01", "value": "9.0"}]))
    assert "HBA1C_POOR_CONTROL" not in t and "HBA1C_ABOVE_GOAL" in t

def test_uses_most_recent_not_worst():
    _, t = types(chart(hba1c=[{"id": "a", "date": "2026-01-01", "value": "10.2"},
                              {"id": "b", "date": "2026-09-01", "value": "6.8"}]))
    assert not t & {"HBA1C_POOR_CONTROL", "HBA1C_ABOVE_GOAL", "HBA1C_OVERDUE"}

def test_old_hba1c_is_overdue_and_cites_last_result():
    ok, _, gaps = evaluate_patient(chart(hba1c=[{"id": "old", "date": "2025-10-01", "value": "6.5"}]), AS_OF)
    g = [x for x in gaps if x.gap_type == "HBA1C_OVERDUE"][0]
    assert g.evidence_ids == ["old"]

def test_kidney_needs_both_labs():
    _, t = types(chart(egfr=[{"id": "e", "date": "2026-06-01", "value": "80"}]))
    assert "KIDNEY_EVAL_DUE" in t
    _, t = types(chart(egfr=[{"id": "e", "date": "2026-06-01", "value": "80"}],
                       uacr=[{"id": "u", "date": "2026-06-01", "value": "20"}]))
    assert "KIDNEY_EVAL_DUE" not in t

def test_eye_exam_window_boundary():
    _, t = types(chart(eye_exams=[{"id": "x", "date": "2025-10-25"}]))   # exactly 365 days ago: outside
    assert "EYE_EXAM_DUE" in t
    _, t = types(chart(eye_exams=[{"id": "x", "date": "2025-10-26"}]))
    assert "EYE_EXAM_DUE" not in t

def test_future_dated_results_are_ignored():
    _, t = types(chart(hba1c=[{"id": "a", "date": "2026-12-01", "value": "6.0"}]))
    assert "HBA1C_OVERDUE" in t
