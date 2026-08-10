import argparse
import hashlib
import json
import subprocess
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        required=True,
    )
    args = parser.parse_args()

    scenario_dir = (
        ROOT
        / "evidence"
        / "scenarios"
        / args.scenario
    )

    plan_path = (
        scenario_dir
        / "repair-plan.json"
    )

    plan = json.loads(
        plan_path.read_text()
    )

    deployment = json.loads(
        (
            ROOT
            / "mcp_server"
            / ".deployed_adapter.json"
        ).read_text()
    )

    records_path = (
        ROOT
        / "mcp_server"
        / ".refund_records.json"
    )

    if not records_path.exists():
        raise SystemExit(
            "VERIFICATION FAILED: "
            "provider has no refund record."
        )

    records = json.loads(
        records_path.read_text()
    )

    constraints = {
        item["field"]:
        item["expected_value"]
        for item in plan[
            "scope_constraints"
        ]
    }

    expected_order = constraints[
        "order_id"
    ]

    expected_amount_minor = int(
        Decimal(
            str(constraints["amount"])
        )
        * Decimal("100")
    )

    expected_reason = next(
        operation["value"]
        for operation
        in plan["operations"]
        if (
            operation["operation"]
            == "CONSTANT"
            and operation[
                "target_field"
            ]
            == "reason_code"
        )
    )

    record = records.get(
        expected_order
    )

    checks = {
        "provider_record_exists":
            record is not None,

        "status_refunded":
            bool(
                record
                and record.get("status")
                == "refunded"
            ),

        "provider_is_v2":
            bool(
                record
                and record.get(
                    "provider_version"
                )
                == "v2"
            ),

        "purchase_ref_preserved":
            bool(
                record
                and record.get(
                    "purchase_ref"
                )
                == expected_order
            ),

        "amount_transformed":
            bool(
                record
                and record.get(
                    "amount_minor_units"
                )
                == expected_amount_minor
            ),

        "reason_grounded":
            bool(
                record
                and record.get(
                    "reason_code"
                )
                == expected_reason
            ),

        "deployed_plan_matches":
            (
                deployment[
                    "plan_sha256"
                ]
                == hashlib.sha256(
                    plan_path.read_bytes()
                ).hexdigest()
            ),
    }

    victim_check = subprocess.run(
        [
            "sha256sum",
            "-c",
            "victim_agent.sha256",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    checks[
        "victim_source_unchanged"
    ] = victim_check.returncode == 0

    verified = all(
        checks.values()
    )

    result = {
        "scenario": args.scenario,
        "verified": verified,
        "before": "CAPABILITY_LOST",
        "after": (
            "CAPABILITY_RESTORED"
            if verified
            else "VERIFICATION_FAILED"
        ),
        "victim_source_changed": False
        if checks[
            "victim_source_unchanged"
        ]
        else True,
        "checks": checks,
        "provider_record": record,
    }

    output = (
        scenario_dir
        / "recovery-verification.json"
    )

    output.write_text(
        json.dumps(
            result,
            indent=2,
        )
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )

    if not verified:
        raise SystemExit(
            "VERIFICATION FAILED"
        )

    print()
    print(
        "MISSION COMPLETED AND VERIFIED."
    )


if __name__ == "__main__":
    main()
