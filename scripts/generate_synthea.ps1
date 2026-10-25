# Optional: regenerate the synthetic patients yourself (needs Java 17+ installed).
# Takes a few minutes and about 5 GB of disk. You do NOT need this to run the app,
# because data/ehr_demo.duckdb is already in the repo.
New-Item -ItemType Directory -Force synthea | Out-Null
Invoke-WebRequest https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar -OutFile synthea/synthea-with-dependencies.jar
java -jar synthea/synthea-with-dependencies.jar -s 42 -p 600 -a 40-85 --exporter.baseDirectory=./synthea/output --exporter.fhir.export=true --exporter.hospital.fhir.export=false --exporter.practitioner.fhir.export=false --exporter.years_of_history=10 Massachusetts
python src/load_fhir.py synthea/output/fhir data/ehr.duckdb
Set-Location src
python run_care_gaps.py ../data/ehr.duckdb 2026-10-25
python run_interactions.py ../data/ehr.duckdb ../data/interactions_seed.csv
