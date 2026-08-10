import asyncio
import json
import sys
from pathlib import Path

from mcp import (
    ClientSession,
    StdioServerParameters,
)

from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]

SERVER = (
    ROOT
    / "mcp_server"
    / "shipment_server.py"
)

AUDIT = (
    ROOT
    / "mcp_server"
    / ".shipment_adapter_audit.jsonl"
)


def extract_structured(result):
    raw = result.model_dump(
        by_alias=True,
        exclude_none=True,
        mode="json",
    )

    structured = (
        raw.get("structuredContent")
        or raw.get("structured_content")
    )

    if structured is not None:
        return structured

    for item in raw.get(
        "content", []
    ):
        text = item.get("text")

        if not text:
            continue

        try:
            parsed = json.loads(text)

            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return None


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
    )

    async with stdio_client(
        params
    ) as (read, write):

        async with ClientSession(
            read,
            write,
        ) as session:

            await session.initialize()

            tools = await session.list_tools()

            tool = next(
                (
                    item
                    for item in tools.tools
                    if item.name
                    == "lookup_shipment"
                ),
                None,
            )

            if tool is None:
                raise SystemExit(
                    "FAIL: lookup_shipment absent."
                )

            tool_data = tool.model_dump(
                by_alias=True,
                exclude_none=True,
                mode="json",
            )

            output_schema = (
                tool_data.get(
                    "outputSchema"
                )
                or tool_data.get(
                    "output_schema"
                )
                or {}
            )

            required = set(
                output_schema.get(
                    "required", []
                )
            )

            expected_required = {
                "status",
                "tracking",
                "carrier",
                "eta_date",
            }

            schema_restored = (
                required
                == expected_required
            )

            result = await session.call_tool(
                "lookup_shipment",
                arguments={
                    "tracking_id":
                        "TRACK-7001"
                },
            )

            structured = (
                extract_structured(result)
            )

    expected_response = {
        "status": "shipped",
        "tracking": "TRACK-7001",
        "carrier": "Northstar Parcel",
        "eta_date": "2026-08-14",
    }

    audit_exists = AUDIT.exists()

    event = None

    if audit_exists:
        lines = [
            line
            for line
            in AUDIT.read_text().splitlines()
            if line.strip()
        ]

        if lines:
            event = json.loads(
                lines[-1]
            )

    checks = {
        "old_output_schema_restored":
            schema_restored,

        "tool_call_returned_old_shape":
            structured
            == expected_response,

        "audit_event_exists":
            event is not None,

        "provider_executed_v2_shape":
            bool(
                event
                and event.get(
                    "raw_v2_response", {}
                ).get(
                    "result", {}
                ).get("state")
                == "in_transit"
            ),

        "response_reconstructed_to_v1":
            bool(
                event
                and event.get(
                    "reconstructed_v1_response"
                )
                == expected_response
            ),

        "scope_is_general":
            bool(
                event
                and event.get("scope")
                == "GENERAL"
            ),
    }

    passed = all(
        checks.values()
    )

    proof = {
        "scenario":
            "response-reshape",

        "proof_type":
            "DIRECT_MCP_BIDIRECTIONAL_CANARY",

        "canary_passed":
            passed,

        # A direct MCP canary is not frozen-agent
        # mission recovery proof.
        "capability_restored":
            False,

        "checks":
            checks,

        "returned_response":
            structured,

        "audit_event":
            event,
    }

    output = (
        ROOT
        / "evidence"
        / "scenarios"
        / "response-reshape"
        / "canary.json"
    )

    output.write_text(
        json.dumps(
            proof,
            indent=2,
        )
    )

    print(
        json.dumps(
            proof,
            indent=2,
        )
    )

    if not passed:
        raise SystemExit(
            "BIDIRECTIONAL CANARY FAILED."
        )

    print()
    print("============================")
    print("BIDIRECTIONAL CANARY PASSED.")
    print("CAPABILITY RESTORED: NOT YET")
    print("============================")


if __name__ == "__main__":
    asyncio.run(main())
