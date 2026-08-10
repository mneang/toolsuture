import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    scenario_dir = (
        ROOT
        / "evidence"
        / "scenarios"
        / args.scenario
    )

    diagnosis = json.loads(
        (scenario_dir / "diagnosis.json").read_text()
    )

    policy = json.loads(
        (scenario_dir / "policy.json").read_text()
    )

    forbidden_action_artifacts = [
        "repair-plan.json",
        "plan-validation.json",
        "action-recovery-verification.json",
        "mission-verification.json",
    ]

    existing_action_artifacts = [
        name
        for name in forbidden_action_artifacts
        if (scenario_dir / name).exists()
    ]

    checks = {
        "diagnosis_refused":
            diagnosis.get("decision") == "REFUSE",

        "risk_is_critical":
            diagnosis.get("risk_level") == "CRITICAL",

        "capability_not_equivalent":
            diagnosis.get("capability_relationship")
            == "NOT_EQUIVALENT",

        "policy_blocked":
            policy.get("gate") == "BLOCKED",

        "auto_repair_denied":
            policy.get("auto_repair_allowed") is False,

        "no_repair_plan_created":
            "repair-plan.json"
            not in existing_action_artifacts,

        "no_execution_artifacts_created":
            len(existing_action_artifacts) == 0,
    }

    verified = all(checks.values())

    result = {
        "scenario": args.scenario,
        "refusal_verified": verified,
        "final_state": (
            "REFUSED_NO_ACTION"
            if verified
            else "REFUSAL_VERIFICATION_FAILED"
        ),
        "reason":
            "Recoverable deletion changed to irreversible permanent deletion.",
        "checks": checks,
        "unexpected_action_artifacts":
            existing_action_artifacts,
    }

    output = (
        scenario_dir
        / "refusal-verification.json"
    )

    output.write_text(
        json.dumps(result, indent=2)
    )

    print(json.dumps(result, indent=2))

    if not verified:
        raise SystemExit(
            "REFUSAL NOT VERIFIED."
        )

    print()
    print("========================")
    print("REFUSAL VERIFIED.")
    print("NO ACTION TAKEN.")
    print("========================")


if __name__ == "__main__":
    main()
