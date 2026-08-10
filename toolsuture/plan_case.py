import argparse
import json
from pathlib import Path
from typing import Literal, Optional, Union

from google import genai
from google.genai import types
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]


class RequestOperation(BaseModel):
    operation: Literal[
        "COPY",
        "MULTIPLY",
        "CONSTANT",
    ]
    source_field: Optional[str] = None
    target_field: str
    factor: Optional[float] = None
    value: Optional[Union[str, int, float]] = None
    evidence: str


class EnumMapEntry(BaseModel):
    source_value: str
    target_value: str


class ResponseOperation(BaseModel):
    operation: Literal[
        "EXTRACT",
        "ENUM_MAP",
        "CONSTANT",
    ]
    source_field: Optional[str] = None
    target_field: str
    value_map: Optional[list[EnumMapEntry]] = None
    value: Optional[Union[str, int, float]] = None
    evidence: str


class ScopeConstraint(BaseModel):
    field: str
    expected_value: Union[str, int, float]


class RepairPlan(BaseModel):
    old_tool: str
    new_tool: str

    scope: Literal[
        "GENERAL",
        "INCIDENT_ONLY",
    ]

    scope_constraints: list[ScopeConstraint]

    request_operations: list[RequestOperation]
    response_operations: list[ResponseOperation]

    rollback_action: Literal[
        "DISABLE_SHIM_AND_ESCALATE"
    ]

    canary_mission: str

    decision: Literal[
        "READY_FOR_VALIDATION",
        "CANNOT_BUILD_SAFE_PLAN",
    ]

    safety_notes: list[str]


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

    mission = (
        scenario_dir / "mission.txt"
    ).read_text()

    diagnosis = json.loads(
        (scenario_dir / "diagnosis.json").read_text()
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

    semantics = json.loads(
        (
            scenario_dir
            / "provider-semantics.json"
        ).read_text()
    )

    prompt = f"""
You are ToolSuture's repair planner.

Create a strictly typed BIDIRECTIONAL compatibility repair plan.

The plan will later be compiled by deterministic code.
You are NOT writing executable Python.

REQUEST OPERATIONS transform OLD tool arguments into NEW tool arguments.

Allowed request operations:

COPY:
pass an old argument to a new argument unchanged.

MULTIPLY:
multiply an old numeric argument by an explicitly supported factor.

CONSTANT:
produce a value explicitly grounded in supplied evidence.

RESPONSE OPERATIONS transform the NEW tool response back into the
OLD response contract expected by the frozen consumer.

Allowed response operations:

EXTRACT:
read a field from a possibly nested NEW response path and expose it
under an OLD response field unchanged.

ENUM_MAP:
read a NEW response field and translate explicitly documented values
into OLD response values.

CONSTANT:
produce an OLD response value only when authoritative evidence makes
that value invariant and unambiguous.

SAFETY RULES:

1. Use only supplied evidence.

2. Every required NEW tool INPUT must be produced by a request operation.

3. If the output contract changed, every required OLD output field must
   be reconstructible by a response operation.

4. Nested response fields must use dot paths such as:
   result.shipment.tracking_id

5. ENUM_MAP requires an explicit value_map grounded in authoritative
   provider semantics. value_map MUST be a list of typed pairs:
   source_value = NEW provider value
   target_value = OLD consumer value.

6. Never infer undocumented enum equivalence.

7. Never invent missing semantics.

8. If a NEW input depends on information found in the USER MISSION but
   not available in OLD TOOL ARGUMENTS, the repair MUST be INCIDENT_ONLY.

9. INCIDENT_ONLY plans must constrain EVERY required OLD argument
   participating in the failed incident.

10. GENERAL is allowed only when the transformation is valid for all
    calls supported by the supplied authoritative evidence.

11. A read-only response reshape may be GENERAL when all mappings are
    authoritative invariants and no incident-specific facts are used.

12. Rollback must be DISABLE_SHIM_AND_ESCALATE.

13. The canary mission must exactly preserve the user's original intent.

14. If either direction cannot be represented safely, return
    CANNOT_BUILD_SAFE_PLAN.

15. Use an empty request_operations or response_operations array only
    when that direction genuinely requires no adaptation.

MISSION:
{mission}

DIAGNOSIS:
{json.dumps(diagnosis, indent=2)}

DETERMINISTIC POLICY:
{json.dumps(policy, indent=2)}

OLD MCP CONTRACT:
{json.dumps(old_contract, indent=2)}

NEW MCP CONTRACT:
{json.dumps(new_contract, indent=2)}

AUTHORITATIVE PROVIDER SEMANTICS:
{json.dumps(semantics, indent=2)}
"""

    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RepairPlan,
            temperature=0,
        ),
    )

    plan = RepairPlan.model_validate_json(
        response.text
    )

    output_path = (
        scenario_dir / "repair-plan.json"
    )

    output_path.write_text(
        plan.model_dump_json(indent=2)
    )

    print(
        plan.model_dump_json(indent=2)
    )

    print()
    print(
        f"Saved -> "
        f"{output_path.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
