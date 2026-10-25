"""The metrics must be able to fail: a writer that drops a finding has to be caught."""
import sys, json, pathlib, duckdb
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
from agent import run_agent
from demo_llm import RulesOnlyLLM

DB = str(ROOT / "data" / "ehr_demo.duckdb")

class Lossy(RulesOnlyLLM):
    def draft(self, pid, tb, feedback=None):
        b = json.loads(super().draft(pid, tb, feedback))
        b["statements"] = [s for s in b["statements"] if s["kind"] != "care_gap"]
        return json.dumps(b)

def test_dropped_gaps_show_up_as_missing():
    con = duckdb.connect(DB, read_only=True)
    pid = con.execute("select patient_id from care_gaps limit 1").fetchone()[0]
    truth = {r[0] for r in con.execute("select gap_type from care_gaps where patient_id=?", [pid]).fetchall()}
    r = run_agent(pid, DB, Lossy())
    predicted = {s["gap_type"] for s in r["brief"]["statements"] if s["kind"] == "care_gap"}
    assert truth - predicted == truth          # recall for this patient is 0, and the metric would show it

def test_every_cohort_patient_gets_a_valid_brief_with_rules_writer():
    con = duckdb.connect(DB, read_only=True)
    for (pid,) in con.execute("select patient_id from cohort").fetchall():
        assert run_agent(pid, DB, RulesOnlyLLM())["status"] == "ready_for_review"
