import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp_server" / "refund_server.py"
VERSION_FILE = ROOT / "mcp_server" / ".provider_version"
RECORDS_FILE = ROOT / "mcp_server" / ".refund_records.json"


async def run_canary(scenario: str):
    scenario_dir = ROOT / "evidence" / "scenarios" / scenario
    output_path = scenario_dir / "adapter-canary.json"

    if VERSION_FILE.read_text().strip() != "v2":
        raise SystemExit("STOP: provider must be v2.")

    # Remove any stale provider result so this canary proves a fresh action.
    if RECORDS_FILE.exists():
        RECORDS_FILE.unlink()

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(tool.name for tool in tools.tools)

            if "refund_order" not in names:
                raise SystemExit(
                    "CANARY FAILED: restored refund_order interface is absent."
                )

            await session.call_tool(
                "refund_order",
                arguments={
                    "order_id": "ORD-1002",
                    "amount": 24.99,
                },
            )

    if not RECORDS_FILE.exists():
        raise SystemExit(
            "CANARY FAILED: v2 provider record was not created."
        )

    records = json.loads(RECORDS_FILE.read_text())
    record = records.get("ORD-1002")

    checks = {
        "old_interface_restored": "refund_order" in names,
        "provider_record_exists": record is not None,
        "provider_is_v2": bool(
            record and record.get("provider_version") == "v2"
        ),
        "purchase_ref_preserved": bool(
            record and record.get("purchase_ref") == "ORD-1002"
        ),
        "amount_became_2499": bool(
            record and record.get("amount_minor_units") == 2499
        ),
        "reason_is_return": bool(
            record and record.get("reason_code") == "RETURN"
        ),
    }

    passed = all(checks.values())

    result = {
        "scenario": scenario,
        "proof_type": "ADAPTER_CANARY_ONLY",
        "canary_passed": passed,

        # Deliberately FALSE:
        # this test does NOT prove the frozen ADK victim recovered.
        "capability_restored": False,

        "checks": checks,
        "provider_record": record,
    }

    output_path.write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))
    print()
    print("IMPORTANT: This proves the adapter only.")
    print("It does NOT prove victim-agent recovery.")

    if not passed:
        raise SystemExit("ADAPTER CANARY FAILED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    asyncio.run(run_canary(args.scenario))


if __name__ == "__main__":
    main()
