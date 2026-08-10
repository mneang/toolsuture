import argparse
import json
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]


class FieldMapping(BaseModel):
    old_field: str
    new_field: str
    mapping_type: Literal[
        "DIRECT_RENAME",
        "UNIT_CONVERSION",
        "SEMANTIC_DERIVATION",
        "NO_EQUIVALENT",
    ]
    transformation: str
    confidence: float = Field(ge=0, le=1)


class UnresolvedRequirement(BaseModel):
    field: str
    why_unresolved: str
    needed_evidence: str


class MigrationDiagnosis(BaseModel):
    old_tool: str
    new_tool: str

    capability_relationship: Literal[
        "LIKELY_EQUIVALENT",
        "PARTIALLY_EQUIVALENT",
        "NOT_EQUIVALENT",
        "UNCERTAIN",
    ]

    field_mappings: list[FieldMapping]
    unresolved_requirements: list[UnresolvedRequirement]

    risk_level: Literal[
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ]

    decision: Literal[
        "AUTO_REPAIR_SAFE",
        "NEEDS_CONTEXT",
        "REQUIRES_APPROVAL",
        "REFUSE",
    ]

    evidence_summary: list[str]
    proposed_adapter_behavior: list[str]
    safety_notes: list[str]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    scenario_dir = ROOT / "evidence" / "scenarios" / args.scenario

    mission = (scenario_dir / "mission.txt").read_text()

    old_contract = json.loads(
        (scenario_dir / "old-contract.json").read_text()
    )

    new_contract = json.loads(
        (scenario_dir / "new-contract.json").read_text()
    )

    provider_semantics = json.loads(
        (scenario_dir / "provider-semantics.json").read_text()
    )

    prompt = f"""
You are ToolSuture's semantic compatibility diagnostician.

Determine whether an OLD MCP tool contract can be safely adapted to a
NEW MCP tool contract for an unchanged deployed agent.

SAFETY RULES:

1. Never invent facts.
2. Similar names do not prove semantic equivalence.
3. Use only the mission, contracts, and authoritative provider semantics.
4. If a required argument cannot be derived, mark it unresolved.
5. Do not return AUTO_REPAIR_SAFE when a required semantic input is unresolved.
6. Distinguish renames, unit conversions, and semantic derivations.
7. The goal is restoring the original user intent safely, not merely making
   the API call succeed.
8. Treat increased destructiveness, irreversibility, permission scope,
   or side effects as a material semantic change. Never classify such a
   migration AUTO_REPAIR_SAFE merely because fields can be mapped.
8. When deriving a required enum, state the exact enum value in the
   transformation.

ORIGINAL USER MISSION:
{mission}

OLD MCP CONTRACT:
{json.dumps(old_contract, indent=2)}

NEW MCP CONTRACT:
{json.dumps(new_contract, indent=2)}

AUTHORITATIVE PROVIDER SEMANTICS:
{json.dumps(provider_semantics, indent=2)}
"""

    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=MigrationDiagnosis,
            temperature=0,
        ),
    )

    diagnosis = MigrationDiagnosis.model_validate_json(response.text)

    output_path = scenario_dir / "diagnosis.json"
    output_path.write_text(
        diagnosis.model_dump_json(indent=2)
    )

    print(diagnosis.model_dump_json(indent=2))
    print()
    print(f"Saved -> {output_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
