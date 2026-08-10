import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("Refund Provider")

ROOT = Path(__file__).resolve().parent

VERSION_FILE = ROOT / ".provider_version"
ADAPTER_FILE = ROOT / ".deployed_adapter.json"
RECORDS_FILE = ROOT / ".refund_records.json"

VERSION = (
    VERSION_FILE.read_text().strip()
    if VERSION_FILE.exists()
    else "v1"
)


def read_records() -> dict:
    if not RECORDS_FILE.exists():
        return {}

    return json.loads(RECORDS_FILE.read_text())


def write_record(record: dict) -> None:
    records = read_records()
    records[record["purchase_ref"]] = record

    RECORDS_FILE.write_text(
        json.dumps(records, indent=2)
    )


def issue_refund_v2_impl(
    purchase_ref: str,
    amount_minor_units: int,
    reason_code: str,
) -> dict:

    allowed_reasons = {
        "RETURN",
        "DAMAGED",
        "FRAUD",
    }

    if reason_code not in allowed_reasons:
        return {
            "status": "error",
            "message": "Invalid reason_code",
            "allowed": sorted(allowed_reasons),
        }

    record = {
        "status": "refunded",
        "purchase_ref": purchase_ref,
        "amount_minor_units": amount_minor_units,
        "currency": "USD",
        "reason_code": reason_code,
        "provider_version": "v2",
        "recorded_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    write_record(record)

    return record


def values_match(actual, expected) -> bool:
    if isinstance(expected, (int, float)):
        try:
            return (
                Decimal(str(actual))
                == Decimal(str(expected))
            )
        except Exception:
            return False

    return actual == expected


def execute_adapter(
    old_args: dict,
    plan: dict,
) -> dict:

    if plan.get("scope") != "INCIDENT_ONLY":
        return {
            "status": "blocked",
            "message": "Only INCIDENT_ONLY repair is allowed in this prototype.",
        }

    if plan.get("old_tool") != "refund_order":
        return {
            "status": "blocked",
            "message": "Unexpected old tool.",
        }

    if plan.get("new_tool") != "issue_refund":
        return {
            "status": "blocked",
            "message": "Unexpected new tool.",
        }

    # Enforce the exact incident boundary.
    for constraint in plan.get(
        "scope_constraints",
        [],
    ):
        field = constraint["field"]
        expected = constraint["expected_value"]

        if field not in old_args:
            return {
                "status": "blocked",
                "message": (
                    f"Missing scoped argument: {field}"
                ),
            }

        if not values_match(
            old_args[field],
            expected,
        ):
            return {
                "status": "blocked",
                "message": (
                    "Compatibility patch scope "
                    f"mismatch for {field}."
                ),
            }

    new_args = {}

    for operation in plan["operations"]:
        kind = operation["operation"]
        source = operation.get(
            "source_field"
        )
        target = operation["target_field"]

        if kind == "COPY":
            new_args[target] = old_args[source]

        elif kind == "MULTIPLY":
            raw_value = Decimal(
                str(old_args[source])
            )

            factor = Decimal(
                str(operation["factor"])
            )

            converted = (
                raw_value * factor
            ).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )

            new_args[target] = int(converted)

        elif kind == "CONSTANT":
            new_args[target] = operation["value"]

        else:
            return {
                "status": "blocked",
                "message": (
                    f"Unsupported operation: {kind}"
                ),
            }

    required = {
        "purchase_ref",
        "amount_minor_units",
        "reason_code",
    }

    if set(new_args) != required:
        return {
            "status": "blocked",
            "message": (
                "Compiled arguments do not "
                "match required v2 fields."
            ),
            "compiled_fields": sorted(
                new_args
            ),
        }

    result = issue_refund_v2_impl(
        purchase_ref=new_args[
            "purchase_ref"
        ],
        amount_minor_units=new_args[
            "amount_minor_units"
        ],
        reason_code=new_args[
            "reason_code"
        ],
    )

    if result.get("status") == "refunded":
        result["toolsuture"] = {
            "compatibility_repair": True,
            "scope": plan["scope"],
            "old_tool": plan["old_tool"],
            "new_tool": plan["new_tool"],
        }

    return result


if VERSION == "v1":

    @mcp.tool()
    def refund_order(
        order_id: str,
        amount: float,
    ) -> dict:
        """Refund an order using the original v1 contract."""

        return {
            "status": "refunded",
            "order_id": order_id,
            "amount": amount,
            "currency": "USD",
            "provider_version": "v1",
        }


else:

    @mcp.tool()
    def issue_refund(
        purchase_ref: str,
        amount_minor_units: int,
        reason_code: str,
    ) -> dict:
        """Native Refund Provider v2 interface."""

        return issue_refund_v2_impl(
            purchase_ref,
            amount_minor_units,
            reason_code,
        )


    if ADAPTER_FILE.exists():
        deployment = json.loads(
            ADAPTER_FILE.read_text()
        )

        if deployment.get("status") == "ACTIVE":

            deployed_plan = deployment[
                "plan"
            ]

            @mcp.tool()
            def refund_order(
                order_id: str,
                amount: float,
            ) -> dict:
                """ToolSuture compatibility interface for a bounded incident."""

                return execute_adapter(
                    {
                        "order_id": order_id,
                        "amount": amount,
                    },
                    deployed_plan,
                )


if __name__ == "__main__":
    mcp.run()
