import sys, pathlib, json, pytest
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
import fhir_sink as f
O = [{"gap_type": "EYE_EXAM_DUE", "description": "Refer for diabetic retinal eye exam"}]

def test_refuses_without_attestation(tmp_path):
    with pytest.raises(PermissionError): f.approve("p1", O, "Dr. A", False, tmp_path)
    assert not (tmp_path / "fhir").exists()

def test_refuses_without_clinician_name(tmp_path):
    with pytest.raises(PermissionError): f.approve("p1", O, "  ", True, tmp_path)

def test_refuses_empty_selection(tmp_path):
    with pytest.raises(ValueError): f.approve("p1", [], "Dr. A", True, tmp_path)

def test_approval_writes_service_request_provenance_and_audit(tmp_path):
    ids = f.approve("p1", O, "Dr. A", True, tmp_path)
    sr = json.loads(next((tmp_path / "fhir").glob("ServiceRequest_*.json")).read_text())
    assert sr["id"] == ids[0] and sr["subject"]["reference"] == "Patient/p1" and sr["requester"]["display"] == "Dr. A"
    assert len(list((tmp_path / "fhir").glob("Provenance_*.json"))) == 1
    assert f.read_audit(tmp_path)[0]["action"] == "approved"

def test_reject_logs_only(tmp_path):
    f.reject("p1", "Dr. A", "no", tmp_path)
    assert not (tmp_path / "fhir").exists() and f.read_audit(tmp_path)[0]["action"] == "rejected"
