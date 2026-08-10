import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ALLOWED_MAPPING_TYPES = {
    "DIRECT_RENAME",
    "UNIT_CONVERSION",
    "SEMANTIC_DERIVATION",
}

MIN_CONFIDENCE = 0.90


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    scenario_dir = ROOT / "evidence" / "scenarios" / args.scenario

    diagnosis = json.loads(
        (scenario_dir / "diagnosis.json").read_text()
    )

    new_contract = json.loads(
        (ROOT / "evidence" / "contracts" / "v2.json").read_text()
    )

    block_reasons = []

    # 1. Gemini itself must classify the repair as safe.
    if diagnosis["decision"] != "AUTO_REPAIR_SAFE":
        block_reasons.append(
            f"Diagnosis decision is {diagnosis['decision']}, "
            "not AUTO_REPAIR_SAFE."
        )

    # 2. No required semantic information may remain unresolved.
    if diagnosis["unresolved_requirements"]:
        unresolved = [
            item["field"]
            for item in diagnosis["unresolved_requirements"]
        ]

        block_reasons.append(
            "Unresolved requirements remain: "
            + ", ".join(unresolved)
        )

    # 3. Automatic repair is only permitted for LOW risk.
    if diagnosis["risk_level"] != "LOW":
        block_reasons.append(
            f"Risk level is {diagnosis['risk_level']}; "
            "automatic repair requires LOW."
        )

    # 4. Every proposed mapping must be from an allowed class.
    for mapping in diagnosis["field_mappings"]:
        mapping_type = mapping["mapping_type"]

        if mapping_type not in ALLOWED_MAPPING_TYPES:
            block_reasons.append(
                f"Unsupported mapping type: {mapping_type}"
            )

        if mapping["confidence"] < MIN_CONFIDENCE:
            block_reasons.append(
                f"Mapping {mapping['old_field']} -> "
                f"{mapping['new_field']} has confidence "
                f"{mapping['confidence']:.2f}, below "
                f"{MIN_CONFIDENCE:.2f}."
            )

    # 5. Find the actual new MCP tool.
    new_tool = None

    for tool in new_contract["tools"]:
        if tool["name"] == diagnosis["new_tool"]:
            new_tool = tool
            break

    if new_tool is None:
        block_reasons.append(
            f"New tool {diagnosis['new_tool']} "
            "does not exist in captured MCP v2 contract."
        )
        required_fields = set()
    else:
        schema = (
            new_tool.get("inputSchema")
            or new_tool.get("input_schema")
            or {}
        )

        required_fields = set(
            schema.get("required", [])
        )

    # 6. Every required v2 parameter must have a usable mapping.
    mapped_fields = {
        mapping["new_field"]
        for mapping in diagnosis["field_mappings"]
        if mapping["mapping_type"] != "NO_EQUIVALENT"
        and mapping["new_field"] not in {
            "N/A",
            "none",
            "None",
        }
    }

    missing_required = sorted(
        required_fields - mapped_fields
    )

    if missing_required:
        block_reasons.append(
            "Required v2 fields without approved mappings: "
            + ", ".join(missing_required)
        )

    result = {
        "scenario": args.scenario,
        "gate": "BLOCKED" if block_reasons else "APPROVED",
        "auto_repair_allowed": not block_reasons,
        "required_v2_fields": sorted(required_fields),
        "mapped_v2_fields": sorted(mapped_fields),
        "minimum_confidence": MIN_CONFIDENCE,
        "block_reasons": block_reasons,
        "source_decision": diagnosis["decision"],
        "risk_level": diagnosis["risk_level"],
    }

    output_path = scenario_dir / "policy.json"
    output_path.write_text(
        json.dumps(result, indent=2)
    )

    print(json.dumps(result, indent=2))
    print()
    print(f"Saved -> {output_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
