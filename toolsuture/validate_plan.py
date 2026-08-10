import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def schema_for(tool):
    return (
        tool.get("inputSchema")
        or tool.get("input_schema")
        or {}
    )


def find_tool(contract, name):
    for tool in contract["tools"]:
        if tool["name"] == name:
            return tool
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    scenario_dir = (
        ROOT / "evidence" / "scenarios" / args.scenario
    )

    plan = json.loads(
        (scenario_dir / "repair-plan.json").read_text()
    )

    policy = json.loads(
        (scenario_dir / "policy.json").read_text()
    )

    old_contract = json.loads(
        (ROOT / "evidence" / "contracts" / "v1.json").read_text()
    )

    new_contract = json.loads(
        (ROOT / "evidence" / "contracts" / "v2.json").read_text()
    )

    reasons = []

    # Fabián must have authorized execution.
    if not policy.get("auto_repair_allowed"):
        reasons.append("Deterministic policy did not authorize auto-repair.")

    if policy.get("gate") != "APPROVED":
        reasons.append("Policy gate is not APPROVED.")

    # Olmo must actually have produced a validatable plan.
    if plan.get("decision") != "READY_FOR_VALIDATION":
        reasons.append(
            f"Repair plan decision is {plan.get('decision')}."
        )

    old_tool = find_tool(old_contract, plan["old_tool"])
    new_tool = find_tool(new_contract, plan["new_tool"])

    if old_tool is None:
        reasons.append("Old tool is absent from captured v1 contract.")
        old_required = set()
        old_properties = set()
    else:
        old_schema = schema_for(old_tool)
        old_required = set(old_schema.get("required", []))
        old_properties = set(
            old_schema.get("properties", {}).keys()
        )

    if new_tool is None:
        reasons.append("New tool is absent from captured v2 contract.")
        new_required = set()
        new_properties = set()
    else:
        new_schema = schema_for(new_tool)
        new_required = set(new_schema.get("required", []))
        new_properties = set(
            new_schema.get("properties", {}).keys()
        )

    # Incident-scoped repairs must bind the complete old call.
    scope_fields = {
        item["field"]
        for item in plan.get("scope_constraints", [])
    }

    if plan.get("scope") == "INCIDENT_ONLY":
        missing_scope = sorted(old_required - scope_fields)

        if missing_scope:
            reasons.append(
                "INCIDENT_ONLY plan does not constrain all required "
                "old-tool arguments: "
                + ", ".join(missing_scope)
            )

    # Every required new field must be produced exactly once.
    operations = plan.get("operations", [])

    targets = [
        operation["target_field"]
        for operation in operations
    ]

    missing_targets = sorted(
        new_required - set(targets)
    )

    if missing_targets:
        reasons.append(
            "Required v2 fields are not produced: "
            + ", ".join(missing_targets)
        )

    duplicate_targets = sorted({
        target
        for target in targets
        if targets.count(target) > 1
    })

    if duplicate_targets:
        reasons.append(
            "Multiple operations write the same target: "
            + ", ".join(duplicate_targets)
        )

    for operation in operations:
        kind = operation["operation"]
        source = operation.get("source_field")
        target = operation["target_field"]

        if target not in new_properties:
            reasons.append(
                f"Operation targets unknown v2 field: {target}"
            )

        if kind == "COPY":
            if source not in old_properties:
                reasons.append(
                    f"COPY references unknown old field: {source}"
                )

        elif kind == "MULTIPLY":
            if source not in old_properties:
                reasons.append(
                    f"MULTIPLY references unknown old field: {source}"
                )

            if operation.get("factor") is None:
                reasons.append(
                    f"MULTIPLY for {target} has no factor."
                )

        elif kind == "CONSTANT":
            if operation.get("value") is None:
                reasons.append(
                    f"CONSTANT for {target} has no value."
                )

        else:
            reasons.append(
                f"Unsupported repair operation: {kind}"
            )

    # Rollback must not depend on a vanished provider version.
    if plan.get("rollback_action") != "DISABLE_SHIM_AND_ESCALATE":
        reasons.append(
            "Rollback must be DISABLE_SHIM_AND_ESCALATE."
        )

    result = {
        "scenario": args.scenario,
        "gate": "BLOCKED" if reasons else "VALIDATED",
        "execution_allowed": not reasons,
        "old_required_fields": sorted(old_required),
        "scope_fields": sorted(scope_fields),
        "new_required_fields": sorted(new_required),
        "operation_targets": sorted(targets),
        "reasons": reasons,
    }

    output = scenario_dir / "plan-validation.json"
    output.write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))
    print()
    print(f"Saved -> {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
