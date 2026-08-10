import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--terminal", required=True)
    args = parser.parse_args()

    scenario_dir = (
        ROOT / "evidence" / "scenarios" / args.scenario
    )

    action_path = (
        scenario_dir
        / "action-recovery-verification.json"
    )

    replay_path = (
        scenario_dir
        / "replay-session.json"
    )

    if not action_path.exists():
        raise SystemExit(
            "FAILED: action recovery verification is missing."
        )

    if not replay_path.exists():
        raise SystemExit(
            "FAILED: replay session is missing."
        )

    terminal_path = Path(args.terminal)

    if not terminal_path.exists():
        raise SystemExit(
            "FAILED: victim terminal transcript is missing."
        )

    action = json.loads(
        action_path.read_text()
    )

    replay = json.loads(
        replay_path.read_text()
    )

    transcript = terminal_path.read_text(
        errors="replace"
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
        "replay_linked_action_verified":
            (
                action.get("proof_level")
                == "REPLAY_LINKED_ACTION_VERIFIED"
                and action.get("action_restored") is True
            ),

        "replay_id_matches":
            (
                action.get("replay_id")
                == replay.get("replay_id")
            ),

        "victim_discovered_tools":
            "ListToolsRequest" in transcript,

        "victim_called_tool":
            "CallToolRequest" in transcript,

        "victim_completed_response":
            (
                "[refund_agent]:" in transcript
                and "successfully processed" in transcript
                and "ORD-1002" in transcript
                and "$24.99" in transcript
            ),

        "no_quota_failure":
            "RESOURCE_EXHAUSTED" not in transcript,

        "no_traceback":
            "Traceback (most recent call last)"
            not in transcript,

        "provider_refund_verified":
            bool(
                action.get(
                    "provider_record", {}
                ).get("status")
                == "refunded"
            ),

        "provider_is_v2":
            bool(
                action.get(
                    "provider_record", {}
                ).get("provider_version")
                == "v2"
            ),

        "victim_source_unchanged":
            victim.returncode == 0,
    }

    mission_completed = all(
        checks.values()
    )

    result = {
        "scenario": args.scenario,
        "replay_id": replay["replay_id"],
        "mission_completed": mission_completed,
        "before": "CAPABILITY_LOST",
        "after": (
            "CAPABILITY_RESTORED"
            if mission_completed
            else "VERIFICATION_FAILED"
        ),
        "victim_source_changed":
            not checks["victim_source_unchanged"],
        "checks": checks,
    }

    output = (
        scenario_dir
        / "mission-verification.json"
    )

    output.write_text(
        json.dumps(result, indent=2)
    )

    print(json.dumps(result, indent=2))

    if not mission_completed:
        raise SystemExit(
            "MISSION NOT COMPLETED AND VERIFIED."
        )

    print()
    print("================================")
    print("MISSION COMPLETED AND VERIFIED.")
    print("================================")


if __name__ == "__main__":
    main()
