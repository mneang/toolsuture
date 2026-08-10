import argparse
import hashlib
import json
from datetime import datetime, timezone
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

    validation = json.loads(
        (
            scenario_dir
            / "plan-validation.json"
        ).read_text()
    )

    policy = json.loads(
        (
            scenario_dir
            / "policy.json"
        ).read_text()
    )

    if (
        validation.get("gate")
        != "VALIDATED"
        or not validation.get(
            "execution_allowed"
        )
    ):
        raise SystemExit(
            "STOP: repair plan is not VALIDATED."
        )

    if (
        policy.get("gate")
        != "APPROVED"
        or not policy.get(
            "auto_repair_allowed"
        )
    ):
        raise SystemExit(
            "STOP: policy did not APPROVE execution."
        )

    plan_bytes = plan_path.read_bytes()

    plan = json.loads(
        plan_bytes
    )

    deployment = {
        "status": "ACTIVE",
        "scenario": args.scenario,
        "plan_sha256": hashlib.sha256(
            plan_bytes
        ).hexdigest(),
        "deployed_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "rollback_action": plan[
            "rollback_action"
        ],
        "plan": plan,
    }

    destination = (
        ROOT
        / "mcp_server"
        / ".deployed_adapter.json"
    )

    destination.write_text(
        json.dumps(
            deployment,
            indent=2,
        )
    )

    print("=== TOOL SUTURE DEPLOYMENT ===")
    print("status: ACTIVE")
    print(
        f"scenario: {args.scenario}"
    )
    print(
        "scope:",
        plan["scope"],
    )
    print(
        "plan_sha256:",
        deployment["plan_sha256"],
    )
    print(
        "rollback:",
        deployment[
            "rollback_action"
        ],
    )


if __name__ == "__main__":
    main()
