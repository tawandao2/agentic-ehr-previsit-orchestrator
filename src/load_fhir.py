"""Flatten Synthea FHIR R4 bundles into DuckDB tables.
Every row keeps the original FHIR resource id so later stages can cite it."""
import glob, json, sys, duckdb

fhir_dir, db_path = sys.argv[1], sys.argv[2]
P, C, O, M, PR, E = [], [], [], [], [], []

def pid(ref):  # "urn:uuid:xxx" or "Patient/xxx" -> xxx
    return ref.split(":")[-1].split("/")[-1] if ref else None

for f in glob.glob(f"{fhir_dir}/*.json"):
    b = json.load(open(f))
    meds = {e["fullUrl"]: e["resource"]["code"]["coding"][0] for e in b["entry"]
            if e["resource"]["resourceType"] == "Medication"}
    for e in b["entry"]:
        r, t = e["resource"], e["resource"]["resourceType"]
        if t == "Patient":
            P.append((r["id"], r["birthDate"], r.get("gender"), r.get("deceasedDateTime")))
        elif t == "Condition":
            c = r["code"]["coding"][0]
            C.append((r["id"], pid(r["subject"]["reference"]), c["code"], c["display"],
                      r["clinicalStatus"]["coding"][0]["code"], r.get("onsetDateTime", "")[:10],
                      (r.get("abatementDateTime") or "")[:10] or None))
        elif t == "Observation" and "valueQuantity" in r:
            c = r["code"]["coding"][0]
            O.append((r["id"], pid(r["subject"]["reference"]), c["code"], c["display"],
                      r["valueQuantity"]["value"], r["valueQuantity"].get("unit"),
                      r["effectiveDateTime"][:10]))
        elif t == "MedicationRequest":
            m = (r.get("medicationCodeableConcept", {}).get("coding") or [None])[0] \
                or meds.get(r.get("medicationReference", {}).get("reference"))
            if m:
                M.append((r["id"], pid(r["subject"]["reference"]), m["code"], m["display"],
                          r["status"], r["authoredOn"][:10]))
        elif t == "Procedure":
            c = r["code"]["coding"][0]
            PR.append((r["id"], pid(r["subject"]["reference"]), c["code"], c["display"],
                       (r.get("performedDateTime") or r.get("performedPeriod", {}).get("start", ""))[:10]))
        elif t == "Encounter":
            c = r["type"][0]["coding"][0]
            E.append((r["id"], pid(r["subject"]["reference"]), c["code"], c["display"],
                      r["period"]["start"][:10]))

con = duckdb.connect(db_path)
specs = {
 "patients":     ("id,birth_date,gender,deceased_date", P),
 "conditions":   ("id,patient_id,code,display,status,onset_date,abatement_date", C),
 "observations": ("id,patient_id,loinc,display,value,unit,effective_date", O),
 "medications":  ("id,patient_id,rxnorm,display,status,authored_date", M),
 "procedures":   ("id,patient_id,snomed,display,performed_date", PR),
 "encounters":   ("id,patient_id,code,display,start_date", E),
}
for name, (cols, rows) in specs.items():
    con.execute(f"DROP TABLE IF EXISTS {name}")
    con.execute(f"CREATE TABLE {name} ({', '.join(c + ' VARCHAR' for c in cols.split(','))})")
    con.executemany(f"INSERT INTO {name} VALUES ({','.join('?'*len(cols.split(',')))})", [tuple(None if v is None else str(v) for v in r) for r in rows])
    print(name, len(rows))
