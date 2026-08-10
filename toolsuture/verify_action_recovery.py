import argparse
import json
import subprocess
from datetime import datetime
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_time(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    scenario_dir = (
        ROOT / "evidence" / "scenarios" / args.scenario
    )

    plan = json.loads(
        (scenario_dir / "repair-plan.json").read_text()
    )

    replay = json.loads(
        (scenario_dir / "replay-session.json").read_text()
    )

    records_path = (
        ROOT / "mcp_server" / ".refund_records.json"
    )

    audit_path = (
        ROOT / "mcp_server" / ".adapter_audit.jsonl"
    )

    if not records_path.exists():
        raise SystemExit(
            "FAILED: provider record absent."
        )

    if not audit_path.exists():
        raise SystemExit(
            "FAILED: adapter audit absent."
        )

    records = json.loads(
        records_path.read_text()
    )

    events = [
        json.loads(line)
        for line in audit_path.read_text().splitlines()
        if line.strip()
    ]

    matching_events = [
        event
        for event in events
        if event.get("replay_id")
        == replay["replay_id"]
    ]

    constraints = {
        item["field"]: item["expected_value"]
        for item in plan["scope_constraints"]
    }

    order_id = constraints["order_id"]

    expected_minor = int(
        Decimal(str(constraints["amount"]))
        * Decimal("100")
    )

    expected_reason = next(
        item["value"]
        for item in plan["operations"]
        if (
            item["operation"] == "CONSTANT"
            and item["target_field"]
            == "reason_code"
        )
    )

    record = records.get(order_id)

    event = (
        matching_events[-1]
        if matching_events
        else None
    )

    victim = subprocess.run(
        [
            "sha256sum",
            "-c",
            "victim_agent.sha256",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    checks = {
        "replay_linked_adapter_event_exists":
            event is not None,

        "adapter_event_after_replay_start":
            bool(
                event
                and parse_time(
                    event["recorded_at"]
                )
                >= parse_time(
                    replay["started_at"]
                )
            ),

        "old_tool_was_refund_order":
            bool(
                event
                and event.get("old_tool")
                == "refund_order"
            ),

        "new_tool_was_issue_refund":
            bool(
                event
                and event.get("new_tool")
                == "issue_refund"
            ),

        "old_order_received":
            bool(
                event
                and event.get(
                    "old_args", {}
                ).get("order_id")
                == order_id
            ),

        "compiled_purchase_ref_correct":
            bool(
                event
                and event.get(
                    "compiled_v2_args", {}
                ).get("purchase_ref")
                == order_id
            ),

        "compiled_amount_correct":
            bool(
                event
                and event.get(
                    "compiled_v2_args", {}
                ).get(
                    "amount_minor_units"
                )
                == expected_minor
            ),

        "compiled_reason_correct":
            bool(
                event
                and event.get(
                    "compiled_v2_args", {}
                ).get("reason_code")
                == expected_reason
            ),

        "provider_record_exists":
            record is not None,

        "provider_is_v2":
            bool(
                record
                and record.get(
                    "provider_version"
                )
                == "v2"
            ),

        "provider_status_refunded":
            bool(
                record
                and record.get("status")
                == "refunded"
            ),

        "victim_source_unchanged":
            victim.returncode == 0,
    }

    verified = all(checks.values())

    result = {
        "scenario": args.scenario,
        "replay_id": replay["replay_id"],
        "proof_level": (
            "REPLAY_LINKED_ACTION_VERIFIED"
            if verified
            else "ACTION_VERIFICATION_FAILED"
        ),
        "action_restored": verified,

        # This verifier deliberately proves action only.
        "mission_completed": False,

        "checks": checks,
        "adapter_event": event,
        "provider_record": record,
    }

    output = (
        scenario_dir
        / "action-recovery-verification.json"
    )

    output.write_text(
        json.dumps(result, indent=2)
    )

    print(json.dumps(result, indent=2))

    if not verified:
        raise SystemExit(
            "ACTION RECOVERY NOT VERIFIED."
        )

    print()
    print(
        "REPLAY-LINKED ACTION VERIFIED."
    )
    print(
        "Full mission completion remains "
        "a separate proof."
    )


if __name__ == "__main__":
    main()
