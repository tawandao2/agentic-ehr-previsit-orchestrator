"""Read-only tools the agent may call. Every result lists the FHIR resource ids
(or rule ids) that back it, and every call is recorded so the brief can be
checked against exactly what the agent was shown."""
import json, re
import duckdb


class ToolBox:
    def __init__(self, db_path):
        self.con = duckdb.connect(db_path, read_only=True)
        self.allowed_ids, self.blob, self.calls = set(), "", []

    def _q(self, sql, *args):
        return self.con.execute(sql, list(args)).fetchall()

    def _record(self, name, patient_id, result):
        self.calls.append((name, patient_id))
        self.allowed_ids |= set(result.get("source_ids", []))
        self.blob += json.dumps(result, default=str) + "\n"
        return result

    def in_cohort(self, patient_id):
        return bool(self._q("select 1 from cohort where patient_id=?", patient_id))

    def get_chart_summary(self, patient_id: str) -> dict:
        """Return the patient's age, active conditions, latest HbA1c and active medications, each with its FHIR resource id."""
        if not self.in_cohort(patient_id):
            return {"error": "patient not found in the diabetes cohort", "source_ids": []}
        age = self._q("select age from cohort where patient_id=?", patient_id)[0][0]
        conds = self._q("select id,display,onset_date from conditions where patient_id=? and status='active' order by onset_date", patient_id)
        a1c = self._q("select id,value,effective_date from observations where patient_id=? and loinc='4548-4' order by effective_date desc limit 1", patient_id)
        meds = self._q("select id,display,authored_date from medications where patient_id=? and status='active'", patient_id)
        res = {"patient_id": patient_id, "age": age,
               "active_conditions": [{"id": i, "name": d, "since": s} for i, d, s in conds],
               "latest_hba1c": ({"id": a1c[0][0], "value_percent": a1c[0][1], "date": a1c[0][2]} if a1c else None),
               "active_medications": [{"id": i, "name": d, "ordered": s} for i, d, s in meds]}
        res["source_ids"] = [x["id"] for x in res["active_conditions"] + res["active_medications"]] + ([a1c[0][0]] if a1c else [])
        return self._record("get_chart_summary", patient_id, res)

    def get_care_gaps(self, patient_id: str) -> dict:
        """Return the care gaps found by the clinical rules engine. A gap's rule id is gap:<TYPE>:<patient_id>."""
        if not self.in_cohort(patient_id):
            return {"error": "patient not found in the diabetes cohort", "source_ids": []}
        rows = self._q("select gap_type,detail,evidence_ids from care_gaps where patient_id=?", patient_id)
        gaps = [{"gap_type": t, "detail": d, "rule_id": f"gap:{t}:{patient_id}", "evidence_ids": list(e or [])} for t, d, e in rows]
        res = {"patient_id": patient_id, "care_gaps": gaps,
               "source_ids": [g["rule_id"] for g in gaps] + [i for g in gaps for i in g["evidence_ids"]]}
        return self._record("get_care_gaps", patient_id, res)

    def get_interaction_alerts(self, patient_id: str) -> dict:
        """Return drug-drug interaction alerts among the patient's active medications."""
        if not self.in_cohort(patient_id):
            return {"error": "patient not found in the diabetes cohort", "source_ids": []}
        rows = self._q("select severity,ingredient_a,ingredient_b,med_ids,note,source from interaction_alerts where patient_id=?", patient_id)
        al = [{"pair": f"{a}+{b}", "severity": s, "med_ids": list(m), "note": n, "source": src} for s, a, b, m, n, src in rows]
        res = {"patient_id": patient_id, "interaction_alerts": al, "source_ids": [i for x in al for i in x["med_ids"]]}
        return self._record("get_interaction_alerts", patient_id, res)

    def as_functions(self):
        """Plain functions with docstrings, in the shape Gemini function calling expects."""
        def get_chart_summary(patient_id: str) -> dict:
            """Return the patient's age, active conditions, latest HbA1c and active medications, each with its FHIR resource id."""
            return self.get_chart_summary(patient_id)
        def get_care_gaps(patient_id: str) -> dict:
            """Return the care gaps found by the clinical rules engine for this patient."""
            return self.get_care_gaps(patient_id)
        def get_interaction_alerts(patient_id: str) -> dict:
            """Return drug-drug interaction alerts among the patient's active medications."""
            return self.get_interaction_alerts(patient_id)
        return [get_chart_summary, get_care_gaps, get_interaction_alerts]
