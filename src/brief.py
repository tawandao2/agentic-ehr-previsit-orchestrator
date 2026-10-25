"""Brief schema, citation validator, and deterministic draft orders."""
import re
from typing import Literal, Optional
from pydantic import BaseModel, Field, ValidationError


class Statement(BaseModel):
    text: str
    kind: Literal["summary", "care_gap", "interaction", "medication"]
    source_ids: list[str] = Field(min_length=1)
    gap_type: Optional[str] = None       # required for care_gap statements
    pair: Optional[str] = None           # required for interaction statements, e.g. "warfarin+aspirin"


class Brief(BaseModel):
    patient_id: str
    statements: list[Statement] = Field(min_length=1, max_length=10)


DRAFT_ORDERS = {
    "HBA1C_OVERDUE": "Order HbA1c (LOINC 4548-4)",
    "HBA1C_POOR_CONTROL": "Order HbA1c (LOINC 4548-4) and review diabetes treatment plan",
    "EYE_EXAM_DUE": "Refer for diabetic retinal eye exam",
    "KIDNEY_EVAL_DUE": "Order eGFR (LOINC 33914-3) and urine albumin/creatinine ratio (LOINC 14959-1)",
}


def draft_orders(gaps):
    """Orders come from the rules, never from the language model. Status is always 'draft'."""
    return [{"gap_type": g["gap_type"], "description": DRAFT_ORDERS[g["gap_type"]],
             "status": "draft", "requires_clinician_attestation": True}
            for g in gaps if g["gap_type"] in DRAFT_ORDERS]


NUM = re.compile(r"\d+(?:\.\d+)?")


def validate(raw_json: str, toolbox, patient_id: str):
    """Returns (brief | None, [problems]). Problems are fed back to the model for one retry."""
    try:
        brief = Brief.model_validate_json(raw_json)
    except ValidationError as e:
        return None, [f"schema: {err['loc']} {err['msg']}" for err in e.errors()[:5]]
    problems = []
    if brief.patient_id != patient_id:
        problems.append(f"patient_id must be {patient_id}")
    for n, s in enumerate(brief.statements, 1):
        bad = [i for i in s.source_ids if i not in toolbox.allowed_ids]
        if bad:
            problems.append(f"statement {n}: cites ids never returned by a tool: {bad}")
        for num in NUM.findall(s.text):
            if not re.search(rf"(?<![\d.]){re.escape(num)}(?![\d])", toolbox.blob):
                problems.append(f"statement {n}: number {num} does not appear in any tool result")
        if s.kind == "care_gap" and not s.gap_type:
            problems.append(f"statement {n}: care_gap statements need gap_type")
        if s.kind == "interaction" and not s.pair:
            problems.append(f"statement {n}: interaction statements need pair")
    return (None if problems else brief), problems
