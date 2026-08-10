import argparse
import json
from pathlib import Path
from typing import Literal, Optional, Union

from google import genai
from google.genai import types
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]


class RepairOperation(BaseModel):
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
    operations: list[RepairOperation]

    rollback_action: Literal["DISABLE_SHIM_AND_ESCALATE"]
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
        scenario_dir
        / "mission.txt"
    ).read_text()

    diagnosis = json.loads(
        (
            scenario_dir
            / "diagnosis.json"
        ).read_text()
    )

    policy = json.loads(
        (
            scenario_dir
            / "policy.json"
        ).read_text()
    )

    old_contract = json.loads(
        (
            ROOT
            / "evidence"
            / "contracts"
            / "v1.json"
        ).read_text()
    )

    new_contract = json.loads(
        (
            ROOT
            / "evidence"
            / "contracts"
            / "v2.json"
        ).read_text()
    )

    semantics = json.loads(
        (
            ROOT
            / "evidence"
            / "provider-v2-semantics.json"
        ).read_text()
    )

    prompt = f"""
You are ToolSuture's repair planner.

Create a strictly typed compatibility repair plan.

The plan will later be compiled by deterministic code.
You are NOT writing executable Python.

SAFETY RULES:

1. Use only supplied evidence.
2. Every required NEW tool argument must be produced by an operation.
3. COPY means pass an old argument into a new argument unchanged.
4. MULTIPLY requires an explicit numeric factor.
5. CONSTANT requires an explicit value grounded in evidence.
6. Never invent missing semantics.
7. If a NEW argument depends on information found in the USER MISSION
   but NOT available in the OLD TOOL ARGUMENTS, the repair MUST be
   INCIDENT_ONLY.
8. INCIDENT_ONLY plans must include scope constraints for EVERY required
   OLD tool argument participating in the failed incident. If the old tool
   requires order_id and amount, constrain BOTH order_id and amount.
9. INCIDENT_ONLY constraints must prevent the patch from silently applying
   to a different call that merely shares one identifier.
10. A GENERAL repair is allowed only when every required NEW argument can
    be derived solely from OLD TOOL arguments or authoritative invariant
    provider rules.
11. Rollback must be DISABLE_SHIM_AND_ESCALATE. Never assume the external
    provider can be reverted to an earlier API version.
12. The canary mission must exactly preserve the user's original intent.
13. If no safe plan can be represented, return CANNOT_BUILD_SAFE_PLAN.

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
        scenario_dir
        / "repair-plan.json"
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
