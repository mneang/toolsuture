import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def input_schema_for(tool):
    return (
        tool.get("inputSchema")
        or tool.get("input_schema")
        or {}
    )


def output_schema_for(tool):
    return (
        tool.get("outputSchema")
        or tool.get("output_schema")
        or {}
    )


def find_tool(contract, name):
    for tool in contract["tools"]:
        if tool["name"] == name:
            return tool
    return None


def resolve_ref(node, root):
    ref = node.get("$ref")

    if not ref:
        return node

    if not ref.startswith("#/"):
        return node

    current = root

    for part in ref[2:].split("/"):
        current = current[part]

    return current


def flatten_schema_paths(schema):
    paths = set()

    def walk(node, prefix=""):
        node = resolve_ref(node, schema)

        properties = node.get(
            "properties", {}
        )

        for name, child in properties.items():
            path = (
                f"{prefix}.{name}"
                if prefix
                else name
            )

            resolved = resolve_ref(
                child,
                schema,
            )

            if resolved.get("properties"):
                walk(resolved, path)
            else:
                paths.add(path)

    walk(schema)

    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    scenario_dir = (
        ROOT
        / "evidence"
        / "scenarios"
        / args.scenario
    )

    plan = json.loads(
        (scenario_dir / "repair-plan.json").read_text()
    )

    policy = json.loads(
        (scenario_dir / "policy.json").read_text()
    )

    old_contract = json.loads(
        (scenario_dir / "old-contract.json").read_text()
    )

    new_contract = json.loads(
        (scenario_dir / "new-contract.json").read_text()
    )

    reasons = []

    if not policy.get("auto_repair_allowed"):
        reasons.append(
            "Deterministic policy did not authorize auto-repair."
        )

    if policy.get("gate") != "APPROVED":
        reasons.append(
            "Policy gate is not APPROVED."
        )

    if plan.get("decision") != "READY_FOR_VALIDATION":
        reasons.append(
            f"Repair plan decision is {plan.get('decision')}."
        )

    old_tool = find_tool(
        old_contract,
        plan["old_tool"],
    )

    new_tool = find_tool(
        new_contract,
        plan["new_tool"],
    )

    if old_tool is None:
        reasons.append(
            "Old tool is absent from captured contract."
        )
        old_input = {}
        old_output = {}
    else:
        old_input = input_schema_for(old_tool)
        old_output = output_schema_for(old_tool)

    if new_tool is None:
        reasons.append(
            "New tool is absent from captured contract."
        )
        new_input = {}
        new_output = {}
    else:
        new_input = input_schema_for(new_tool)
        new_output = output_schema_for(new_tool)

    old_required = set(
        old_input.get("required", [])
    )

    old_properties = set(
        old_input.get(
            "properties", {}
        ).keys()
    )

    new_required = set(
        new_input.get("required", [])
    )

    new_properties = set(
        new_input.get(
            "properties", {}
        ).keys()
    )

    scope_fields = {
        item["field"]
        for item in plan.get(
            "scope_constraints", []
        )
    }

    if plan.get("scope") == "INCIDENT_ONLY":
        missing_scope = sorted(
            old_required - scope_fields
        )

        if missing_scope:
            reasons.append(
                "INCIDENT_ONLY plan does not constrain all required "
                "old-tool arguments: "
                + ", ".join(missing_scope)
            )

    # Backward compatibility with our already-proven refund plan.
    request_operations = plan.get(
        "request_operations"
    )

    if request_operations is None:
        request_operations = plan.get(
            "operations", []
        )

    request_targets = [
        operation["target_field"]
        for operation in request_operations
    ]

    missing_request_targets = sorted(
        new_required
        - set(request_targets)
    )

    if missing_request_targets:
        reasons.append(
            "Required v2 input fields are not produced: "
            + ", ".join(
                missing_request_targets
            )
        )

    duplicate_request_targets = sorted({
        target
        for target in request_targets
        if request_targets.count(target) > 1
    })

    if duplicate_request_targets:
        reasons.append(
            "Multiple request operations write the same target: "
            + ", ".join(
                duplicate_request_targets
            )
        )

    for operation in request_operations:
        kind = operation["operation"]
        source = operation.get(
            "source_field"
        )
        target = operation[
            "target_field"
        ]

        if target not in new_properties:
            reasons.append(
                f"Request operation targets unknown "
                f"v2 input field: {target}"
            )

        if kind == "COPY":
            if source not in old_properties:
                reasons.append(
                    f"COPY references unknown "
                    f"old input field: {source}"
                )

        elif kind == "MULTIPLY":
            if source not in old_properties:
                reasons.append(
                    f"MULTIPLY references unknown "
                    f"old input field: {source}"
                )

            if operation.get("factor") is None:
                reasons.append(
                    f"MULTIPLY for {target} "
                    "has no factor."
                )

        elif kind == "CONSTANT":
            if operation.get("value") is None:
                reasons.append(
                    f"CONSTANT for {target} "
                    "has no value."
                )

        else:
            reasons.append(
                f"Unsupported request operation: {kind}"
            )

    # ---------- RESPONSE VALIDATION ----------

    response_operations = plan.get(
        "response_operations", []
    )

    old_output_required = set(
        old_output.get("required", [])
    )

    old_output_properties = set(
        old_output.get(
            "properties", {}
        ).keys()
    )

    new_output_paths = flatten_schema_paths(
        new_output
    )

    response_targets = [
        operation["target_field"]
        for operation in response_operations
    ]

    output_changed = (
        old_output != new_output
    )

    if output_changed and old_output_required:
        missing_response_targets = sorted(
            old_output_required
            - set(response_targets)
        )

        if missing_response_targets:
            reasons.append(
                "Required old response fields "
                "cannot be reconstructed: "
                + ", ".join(
                    missing_response_targets
                )
            )

    duplicate_response_targets = sorted({
        target
        for target in response_targets
        if response_targets.count(target) > 1
    })

    if duplicate_response_targets:
        reasons.append(
            "Multiple response operations write "
            "the same old response field: "
            + ", ".join(
                duplicate_response_targets
            )
        )

    for operation in response_operations:
        kind = operation["operation"]
        source = operation.get(
            "source_field"
        )
        target = operation[
            "target_field"
        ]

        if target not in old_output_properties:
            reasons.append(
                f"Response operation targets unknown "
                f"old output field: {target}"
            )

        if kind in {
            "EXTRACT",
            "ENUM_MAP",
        }:
            if source not in new_output_paths:
                reasons.append(
                    f"{kind} references unknown "
                    f"v2 response path: {source}"
                )

        if kind == "ENUM_MAP":
            value_map = operation.get(
                "value_map"
            )

            if not value_map:
                reasons.append(
                    f"ENUM_MAP for {target} "
                    "has no value_map."
                )

        elif kind == "CONSTANT":
            if operation.get("value") is None:
                reasons.append(
                    f"Response CONSTANT for {target} "
                    "has no value."
                )

        elif kind != "EXTRACT":
            if kind != "ENUM_MAP":
                reasons.append(
                    f"Unsupported response operation: "
                    f"{kind}"
                )

    if plan.get(
        "rollback_action"
    ) != "DISABLE_SHIM_AND_ESCALATE":
        reasons.append(
            "Rollback must be DISABLE_SHIM_AND_ESCALATE."
        )

    result = {
        "scenario": args.scenario,
        "gate": (
            "BLOCKED"
            if reasons
            else "VALIDATED"
        ),
        "execution_allowed":
            not reasons,

        "old_required_input_fields":
            sorted(old_required),

        "new_required_input_fields":
            sorted(new_required),

        "request_operation_targets":
            sorted(request_targets),

        "old_required_response_fields":
            sorted(old_output_required),

        "new_response_paths":
            sorted(new_output_paths),

        "response_operation_targets":
            sorted(response_targets),

        "output_contract_changed":
            output_changed,

        "scope_fields":
            sorted(scope_fields),

        "reasons":
            reasons,
    }

    output = (
        scenario_dir
        / "plan-validation.json"
    )

    output.write_text(
        json.dumps(result, indent=2)
    )

    print(
        json.dumps(result, indent=2)
    )

    print()
    print(
        f"Saved -> "
        f"{output.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
