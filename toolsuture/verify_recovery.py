import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--agent-log", required=True)
    args = parser.parse_args()

    scenario_dir = ROOT / "evidence" / "scenarios" / args.scenario

    plan_path = scenario_dir / "repair-plan.json"
    replay_path = scenario_dir / "replay-session.json"
    records_path = ROOT / "mcp_server" / ".refund_records.json"
    deployment_path = ROOT / "mcp_server" / ".deployed_adapter.json"

    if not replay_path.exists():
        raise SystemExit(
            "VERIFICATION REFUSED: no armed victim replay session."
        )

    if not records_path.exists():
        raise SystemExit(
            "VERIFICATION FAILED: no fresh provider record."
        )

    agent_log = Path(args.agent_log)

    if not agent_log.exists():
        raise SystemExit(
            f"VERIFICATION FAILED: agent log not found: {agent_log}"
        )

    log_text = agent_log.read_text(errors="replace")

    plan = json.loads(plan_path.read_text())
    replay = json.loads(replay_path.read_text())
    records = json.loads(records_path.read_text())
    deployment = json.loads(deployment_path.read_text())

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
        operation["value"]
        for operation in plan["operations"]
        if operation["operation"] == "CONSTANT"
        and operation["target_field"] == "reason_code"
    )

    record = records.get(order_id)

    replay_started = parse_time(replay["started_at"])

    record_after_replay = False

    if record and record.get("recorded_at"):
        record_after_replay = (
            parse_time(record["recorded_at"])
            >= replay_started
        )

    victim = subprocess.run(
        ["sha256sum", "-c", "victim_agent.sha256"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    checks = {
        # Agent-level proof
        "agent_log_has_tool_call":
            "Processing request of type CallToolRequest" in log_text,

        "agent_log_has_no_quota_failure":
            "RESOURCE_EXHAUSTED" not in log_text,

        # Freshness proof — prevents a canary result being reused.
        "provider_record_created_after_replay_started":
            record_after_replay,

        # External-state verification
        "provider_record_exists":
            record is not None,

        "status_refunded":
            bool(record and record.get("status") == "refunded"),

        "provider_is_v2":
            bool(record and record.get("provider_version") == "v2"),

        "purchase_ref_preserved":
            bool(record and record.get("purchase_ref") == order_id),

        "amount_transformed":
            bool(
                record
                and record.get("amount_minor_units") == expected_minor
            ),

        "reason_grounded":
            bool(
                record
                and record.get("reason_code") == expected_reason
            ),

        # Deployment proof
        "deployed_plan_matches":
            deployment["plan_sha256"]
            == hashlib.sha256(plan_path.read_bytes()).hexdigest(),

        # Judge-money proof
        "victim_source_unchanged":
            victim.returncode == 0,
    }

    verified = all(checks.values())

    result = {
        "scenario": args.scenario,
        "verified": verified,
        "before": "CAPABILITY_LOST",
        "after": (
            "CAPABILITY_RESTORED"
            if verified
            else "VERIFICATION_FAILED"
        ),
        "victim_source_changed":
            not checks["victim_source_unchanged"],
        "checks": checks,
        "provider_record": record,
    }

    output = scenario_dir / "recovery-verification.json"
    output.write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))

    if not verified:
        raise SystemExit(
            "MISSION NOT VERIFIED."
        )

    print()
    print("MISSION COMPLETED AND VERIFIED.")


if __name__ == "__main__":
    main()
