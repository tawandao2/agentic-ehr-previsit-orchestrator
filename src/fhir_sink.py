"""Simulated 'push to EHR'. Nothing is written until a named clinician attests.

Approved orders become FHIR R4 ServiceRequest resources plus a Provenance
resource, saved as JSON files in a local outbox folder. This is a stand-in for
a FHIR test server (for example HAPI): swapping it in means POSTing the same
JSON instead of saving it. Every decision, approve or reject, is appended to an
audit log.
"""
import json, uuid, pathlib
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _audit(outbox, entry):
    outbox = pathlib.Path(outbox); outbox.mkdir(parents=True, exist_ok=True)
    with open(outbox / "audit_log.jsonl", "a") as f:
        f.write(json.dumps({"at": _now(), **entry}) + "\n")


def approve(patient_id, orders, clinician, attested, outbox):
    if not attested:
        raise PermissionError("Clinician attestation is required before anything is written.")
    if not clinician or not clinician.strip():
        raise PermissionError("A named clinician is required.")
    if not orders:
        raise ValueError("No orders selected.")
    outbox = pathlib.Path(outbox); (outbox / "fhir").mkdir(parents=True, exist_ok=True)
    written = []
    for o in orders:
        sr_id = str(uuid.uuid4())
        sr = {"resourceType": "ServiceRequest", "id": sr_id, "status": "active", "intent": "order",
              "subject": {"reference": f"Patient/{patient_id}"}, "code": {"text": o["description"]},
              "authoredOn": _now(), "requester": {"display": clinician.strip()},
              "note": [{"text": f"Drafted by an AI-assisted workflow for care gap {o['gap_type']}; approved by a clinician."}]}
        prov = {"resourceType": "Provenance", "id": str(uuid.uuid4()),
                "target": [{"reference": f"ServiceRequest/{sr_id}"}], "recorded": _now(),
                "agent": [{"type": {"text": "author"}, "who": {"display": clinician.strip()}},
                          {"type": {"text": "assembler"}, "who": {"display": "AI pre-visit orchestrator (synthetic data demo)"}}]}
        for res in (sr, prov):
            (outbox / "fhir" / f"{res['resourceType']}_{res['id']}.json").write_text(json.dumps(res, indent=2))
        written.append(sr_id)
    _audit(outbox, {"action": "approved", "patient_id": patient_id, "clinician": clinician.strip(),
                    "orders": [o["description"] for o in orders], "service_request_ids": written})
    return written


def reject(patient_id, clinician, reason, outbox):
    _audit(outbox, {"action": "rejected", "patient_id": patient_id,
                    "clinician": (clinician or "").strip() or "unnamed", "reason": reason})


def read_audit(outbox):
    p = pathlib.Path(outbox) / "audit_log.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
