import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp_server" / "refund_server.py"
RECORDS_FILE = ROOT / "mcp_server" / ".refund_records.json"


def read_records():
    if not RECORDS_FILE.exists():
        return {}
    return json.loads(RECORDS_FILE.read_text())


def extract_payload(result):
    for item in result.content:
        text = getattr(item, "text", None)

        if not text:
            continue

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue

    return {}


async def call_refund(order_id, amount):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "refund_order",
                arguments={
                    "order_id": order_id,
                    "amount": amount,
                },
            )

            return extract_payload(result)


async def main(scenario):
    scenario_dir = (
        ROOT / "evidence" / "scenarios" / scenario
    )

    plan = json.loads(
        (scenario_dir / "repair-plan.json").read_text()
    )

    constraints = {
        item["field"]: item["expected_value"]
        for item in plan["scope_constraints"]
    }

    expected_order = constraints["order_id"]
    expected_amount = constraints["amount"]

    cases = [
        {
            "name": "wrong_order",
            "order_id": expected_order + "-OUTSIDE-SCOPE",
            "amount": expected_amount,
        },
        {
            "name": "wrong_amount",
            "order_id": expected_order,
            "amount": float(expected_amount) + 1.00,
        },
    ]

    results = []

    for case in cases:
        if RECORDS_FILE.exists():
            RECORDS_FILE.unlink()

        payload = await call_refund(
            case["order_id"],
            case["amount"],
        )

        records = read_records()

        passed = (
            payload.get("status") == "blocked"
            and len(records) == 0
        )

        results.append({
            "case": case["name"],
            "input": {
                "order_id": case["order_id"],
                "amount": case["amount"],
            },
            "adapter_response": payload,
            "provider_records_created": len(records),
            "scope_guard_passed": passed,
        })

    all_passed = all(
        item["scope_guard_passed"]
        for item in results
    )

    output = {
        "scenario": scenario,
        "test": "INCIDENT_SCOPE_GUARD",
        "passed": all_passed,
        "results": results,
    }

    output_path = (
        scenario_dir / "scope-guard-test.json"
    )

    output_path.write_text(
        json.dumps(output, indent=2)
    )

    print(json.dumps(output, indent=2))

    if not all_passed:
        raise SystemExit(
            "SCOPE GUARD FAILED"
        )

    print()
    print("INCIDENT SCOPE GUARD VERIFIED.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    asyncio.run(main(args.scenario))
