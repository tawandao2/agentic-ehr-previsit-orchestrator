"""Rules-only stand-in for the language model, so the app and tests run with no API key.
It writes the brief by copying tool output; no AI is involved."""
import json


class RulesOnlyLLM:
    def draft(self, patient_id, tb, feedback=None):
        s, g, i = tb.get_chart_summary(patient_id), tb.get_care_gaps(patient_id), tb.get_interaction_alerts(patient_id)
        if "error" in s:
            return json.dumps({"patient_id": patient_id, "statements": []})
        cond = s["active_conditions"][0]["id"] if s["active_conditions"] else s["source_ids"][0]
        a1c = s["latest_hba1c"]
        text = f"Age {s['age']}, type 2 diabetes." + (f" Latest HbA1c {a1c['value_percent']}% on {a1c['date']}." if a1c else "")
        st = [{"text": text, "kind": "summary", "source_ids": [cond] + ([a1c["id"]] if a1c else [])}]
        st += [{"text": x["detail"], "kind": "care_gap", "source_ids": [x["rule_id"]], "gap_type": x["gap_type"]} for x in g["care_gaps"]]
        st += [{"text": f"{x['severity']} interaction, {x['pair']}: {x['note']}", "kind": "interaction",
                "source_ids": x["med_ids"], "pair": x["pair"]} for x in i["interaction_alerts"]]
        return json.dumps({"patient_id": patient_id, "statements": st[:10]})
