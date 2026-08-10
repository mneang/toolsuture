import json
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]

OLD_CONTRACT = json.loads(
    (ROOT / "evidence" / "contracts" / "v1.json").read_text()
)

NEW_CONTRACT = json.loads(
    (ROOT / "evidence" / "contracts" / "v2.json").read_text()
)


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


MISSION = """
Refund order ORD-1001 for $49.99.
"""

INCIDENT = """
The exact same frozen ADK refund agent previously completed this mission
successfully against provider v1.

The external provider changed to v2.

The victim agent's source files and prompt were not modified.

After the provider change, the agent discovered the MCP server but made
no refund tool call and did not complete the refund.
"""


prompt = f"""
You are ToolSuture's semantic compatibility diagnostician.

Your task is to determine whether an OLD MCP tool contract can be safely
adapted to a NEW MCP tool contract for an unchanged deployed agent.

IMPORTANT SAFETY RULES:

1. Do not invent facts that are not present in the evidence.
2. A similar field name does not automatically prove semantic equivalence.
3. If the new tool requires information that cannot be derived from the
   mission, old contract, new contract, or incident evidence, mark that
   requirement unresolved.
4. If any required semantic input is unresolved, do NOT return
   AUTO_REPAIR_SAFE.
5. Distinguish simple renames from unit conversions and semantic changes.
6. We care about restoring the original capability safely, not merely
   making the API call succeed.

ORIGINAL USER MISSION:
{MISSION}

INCIDENT:
{INCIDENT}

OLD MCP CONTRACT:
{json.dumps(OLD_CONTRACT, indent=2)}

NEW MCP CONTRACT:
{json.dumps(NEW_CONTRACT, indent=2)}
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

output_path = ROOT / "evidence" / "gate-1c-diagnosis.json"
output_path.write_text(
    diagnosis.model_dump_json(indent=2)
)

print(diagnosis.model_dump_json(indent=2))
print()
print(f"Saved -> {output_path.relative_to(ROOT)}")
