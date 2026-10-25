"""Run the rules over every patient in DuckDB and write the care_gaps table."""
import sys, duckdb
from datetime import date
from care_gaps import evaluate_patient

db, as_of = sys.argv[1], date.fromisoformat(sys.argv[2])
con = duckdb.connect(db)
def rows(sql): return con.execute(sql).fetchall()

patients = rows("select id, birth_date from patients where deceased_date is null")
by = lambda sql: {}
def group(sql):
    out = {}
    for pid, *rest in rows(sql): out.setdefault(pid, []).append(rest)
    return out
cond = group("select patient_id,id,code,status from conditions")
obs = group("select patient_id,id,loinc,effective_date,value from observations where loinc in ('4548-4','33914-3','14959-1')")
eye = group("select patient_id,id,performed_date from procedures where snomed='722161008'")

con.execute("DROP TABLE IF EXISTS care_gaps")
con.execute("CREATE TABLE care_gaps (patient_id VARCHAR, as_of DATE, gap_type VARCHAR, detail VARCHAR, evidence_ids VARCHAR[])")
con.execute("DROP TABLE IF EXISTS cohort")
con.execute("CREATE TABLE cohort (patient_id VARCHAR, age INT, n_gaps INT)")
n = 0
for pid, bd in patients:
    o = lambda code: [{"id": i, "date": d, "value": v} for i, c, d, v in obs.get(pid, []) if c == code]
    chart = {"patient_id": pid, "birth_date": bd,
             "conditions": [{"id": i, "code": c, "status": s} for i, c, s in cond.get(pid, [])],
             "hba1c": o("4548-4"), "egfr": o("33914-3"), "uacr": o("14959-1"),
             "eye_exams": [{"id": i, "date": d} for i, d in eye.get(pid, [])]}
    ok, reason, gaps = evaluate_patient(chart, as_of)
    if not ok: continue
    n += 1
    con.execute("INSERT INTO cohort VALUES (?,?,?)", [pid, int(reason.split()[1]), len(gaps)])
    for g in gaps:
        con.execute("INSERT INTO care_gaps VALUES (?,?,?,?,?)", [pid, as_of, g.gap_type, g.detail, g.evidence_ids])
print("cohort", n)
for r in rows("select gap_type,count(*),count(distinct patient_id) from care_gaps group by 1 order by 2 desc"): print(r)
print("patients with zero gaps:", rows("select count(*) from cohort where n_gaps=0")[0][0])
