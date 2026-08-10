import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSIS_PATH = ROOT / "evidence" / "gate-1c-diagnosis.json"
OUTPUT_PATH = ROOT / "evidence" / "gate-1d-policy.json"


diagnosis = json.loads(DIAGNOSIS_PATH.read_text())

block_reasons = []

if diagnosis["decision"] != "AUTO_REPAIR_SAFE":
    block_reasons.append(
        f"Gemini decision is {diagnosis['decision']}, not AUTO_REPAIR_SAFE."
    )

if diagnosis["unresolved_requirements"]:
    fields = [
        item["field"]
        for item in diagnosis["unresolved_requirements"]
    ]
    block_reasons.append(
        "Required semantic inputs remain unresolved: "
        + ", ".join(fields)
    )

if diagnosis["risk_level"] in {"HIGH", "CRITICAL"}:
    block_reasons.append(
        f"Risk level is {diagnosis['risk_level']}."
    )

low_confidence = [
    mapping
    for mapping in diagnosis["field_mappings"]
    if mapping["confidence"] < 0.80
    and mapping["mapping_type"] != "NO_EQUIVALENT"
]

if low_confidence:
    block_reasons.append(
        "One or more proposed mappings are below the confidence threshold."
    )


result = {
    "gate": "BLOCKED" if block_reasons else "APPROVED",
    "auto_repair_allowed": not block_reasons,
    "block_reasons": block_reasons,
    "source_decision": diagnosis["decision"],
    "risk_level": diagnosis["risk_level"],
}

OUTPUT_PATH.write_text(json.dumps(result, indent=2))

print(json.dumps(result, indent=2))
print()
print(f"Saved -> {OUTPUT_PATH.relative_to(ROOT)}")
