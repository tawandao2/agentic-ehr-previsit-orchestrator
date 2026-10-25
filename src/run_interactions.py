import sys, duckdb
from interactions import load_seed, check_patient

db, table_path = sys.argv[1], sys.argv[2]
table = load_seed(table_path)
con = duckdb.connect(db)
meds = {}
for pid, i, d, s in con.execute("select patient_id,id,display,status from medications where patient_id in (select patient_id from cohort)").fetchall():
    meds.setdefault(pid, []).append({"id": i, "display": d, "status": s})
con.execute("DROP TABLE IF EXISTS interaction_alerts")
con.execute("CREATE TABLE interaction_alerts (patient_id VARCHAR, severity VARCHAR, ingredient_a VARCHAR, ingredient_b VARCHAR, med_ids VARCHAR[], note VARCHAR, source VARCHAR)")
for pid, m in meds.items():
    for a in check_patient(pid, m, table):
        con.execute("INSERT INTO interaction_alerts VALUES (?,?,?,?,?,?,?)", [a.patient_id, a.severity, a.ingredient_a, a.ingredient_b, a.med_ids, a.note, a.source])
print(con.execute("select severity,ingredient_a,ingredient_b,count(*) from interaction_alerts group by all order by 4 desc").fetchall())
print("patients with >=1 alert:", con.execute("select count(distinct patient_id) from interaction_alerts").fetchone()[0], "of", len(meds))
