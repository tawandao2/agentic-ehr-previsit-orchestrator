import sys, json, pathlib, duckdb, pytest
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
from agent import run_agent

P = "pat-1"

@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "t.duckdb")
    c = duckdb.connect(path)
    c.execute("create table cohort (patient_id varchar, age int, n_gaps int)")
    c.execute("create table conditions (id varchar, patient_id varchar, code varchar, display varchar, status varchar, onset_date varchar, abatement_date varchar)")
    c.execute("create table observations (id varchar, patient_id varchar, loinc varchar, display varchar, value varchar, unit varchar, effective_date varchar)")
    c.execute("create table medications (id varchar, patient_id varchar, rxnorm varchar, display varchar, status varchar, authored_date varchar)")
    c.execute("create table care_gaps (patient_id varchar, as_of date, gap_type varchar, detail varchar, evidence_ids varchar[])")
    c.execute("create table interaction_alerts (patient_id varchar, severity varchar, ingredient_a varchar, ingredient_b varchar, med_ids varchar[], note varchar, source varchar)")
    c.execute("insert into cohort values (?,62,2)", [P])
    c.execute("insert into conditions values ('cond-1',?,'44054006','Diabetes mellitus type 2','active','2015-01-01',null)", [P])
    c.execute("insert into observations values ('obs-1',?,'4548-4','HbA1c','7.4','%','2026-08-01')", [P])
    c.execute("insert into medications values ('med-1',?,'1','Simvastatin 20 MG','active','2026-01-01')", [P])
    c.execute("insert into medications values ('med-2',?,'2','amLODIPine 2.5 MG','active','2026-01-01')", [P])
    c.execute("insert into care_gaps values (?, '2026-10-25','EYE_EXAM_DUE','No diabetic retinal eye exam in the last 12 months (none on record)',[])", [P])
    c.execute("insert into care_gaps values (?, '2026-10-25','HBA1C_ABOVE_GOAL','Most recent HbA1c 7.4% on 2026-08-01 (at or above 7.0%)',['obs-1'])", [P])
    c.execute("insert into interaction_alerts values (?, 'Moderate','simvastatin','amlodipine',['med-1','med-2'],'dose limit','FDA')", [P])
    c.close()
    return path

class Fake:
    """Stands in for Gemini. `script` builds the JSON from what the tools return."""
    def __init__(self, script, call_tools=True):
        self.script, self.call_tools, self.n = script, call_tools, 0
    def draft(self, pid, tb, feedback=None):
        self.n += 1
        if self.call_tools and self.n == 1:
            tb.get_chart_summary(pid); tb.get_care_gaps(pid); tb.get_interaction_alerts(pid)
        return self.script(pid, self.n)

def good(pid, n):
    return json.dumps({"patient_id": pid, "statements": [
        {"text": "62-year-old with type 2 diabetes, latest HbA1c 7.4%.", "kind": "summary", "source_ids": ["cond-1", "obs-1"]},
        {"text": "No diabetic eye exam on record in the last 12 months.", "kind": "care_gap", "source_ids": [f"gap:EYE_EXAM_DUE:{pid}"], "gap_type": "EYE_EXAM_DUE"},
        {"text": "Simvastatin and amlodipine interact (dose limit).", "kind": "interaction", "source_ids": ["med-1", "med-2"], "pair": "simvastatin+amlodipine"}]})

def test_happy_path_and_orders_come_from_rules(db):
    r = run_agent(P, db, Fake(good))
    assert r["status"] == "ready_for_review" and r["attempts"] == 1
    assert [o["gap_type"] for o in r["draft_orders"]] == ["EYE_EXAM_DUE"]
    assert all(o["status"] == "draft" and o["requires_clinician_attestation"] for o in r["draft_orders"])

def test_unknown_patient_is_refused(db):
    assert run_agent("nope", db, Fake(good))["status"] == "refused"

def test_invented_citation_is_rejected(db):
    bad = lambda pid, n: json.dumps({"patient_id": pid, "statements": [{"text": "x", "kind": "summary", "source_ids": ["made-up-id"]}]})
    r = run_agent(P, db, Fake(bad))
    assert r["status"] == "rejected" and "made-up-id" in r["problems"][0]

def test_invented_number_is_rejected(db):
    bad = lambda pid, n: json.dumps({"patient_id": pid, "statements": [{"text": "HbA1c was 9.8%.", "kind": "summary", "source_ids": ["obs-1"]}]})
    r = run_agent(P, db, Fake(bad))
    assert r["status"] == "rejected" and any("9.8" in p for p in r["problems"])

def test_retry_fixes_a_bad_first_answer(db):
    r = run_agent(P, db, Fake(lambda pid, n: "not json" if n == 1 else good(pid, n)))
    assert r["status"] == "ready_for_review" and r["attempts"] == 2

def test_skipping_the_tools_is_rejected(db):
    r = run_agent(P, db, Fake(good, call_tools=False))
    assert r["status"] == "rejected"

def test_wrong_patient_id_in_brief_is_rejected(db):
    r = run_agent(P, db, Fake(lambda pid, n: good("other", n)))
    assert r["status"] == "rejected"
