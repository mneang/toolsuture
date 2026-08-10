import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SCENARIO = "response-reshape"

SCENARIO_DIR = (
    ROOT
    / "evidence"
    / "scenarios"
    / SCENARIO
)

AUDIT_FILE = (
    ROOT
    / "mcp_server"
    / ".shipment_adapter_audit.jsonl"
)

DEPLOYMENT_FILE = (
    ROOT
    / "mcp_server"
    / ".deployed_adapter.json"
)

VERSION_FILE = (
    ROOT
    / "mcp_server"
    / ".shipment_provider_version"
)


def parse_time(value):
    return datetime.fromisoformat(
        value.replace(
            "Z",
            "+00:00",
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--terminal",
        required=True,
    )
    args = parser.parse_args()

    replay = json.loads(
        (
            SCENARIO_DIR
            / "replay-session.json"
        ).read_text()
    )

    deployment = json.loads(
        DEPLOYMENT_FILE.read_text()
    )

    transcript = Path(
        args.terminal
    ).read_text(
        errors="replace"
    )

    events = []

    if AUDIT_FILE.exists():
        events = [
            json.loads(line)
            for line
            in AUDIT_FILE.read_text().splitlines()
            if line.strip()
        ]

    matching = [
        event
        for event in events
        if event.get("replay_id")
        == replay["replay_id"]
    ]

    event = (
        matching[-1]
        if matching
        else None
    )

    victim = subprocess.run(
        [
            "sha256sum",
            "-c",
            "shipment_victim.sha256",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    expected_v1 = {
        "status": "shipped",
        "tracking": "TRACK-7001",
        "carrier": "Northstar Parcel",
        "eta_date": "2026-08-14",
    }

    event_is_fresh = bool(
        event
        and parse_time(
            event["recorded_at"]
        )
        >= parse_time(
            replay["started_at"]
        )
    )

    checks = {
        "provider_still_v2":
            VERSION_FILE.read_text().strip()
            == "v2",

        "adapter_still_active":
            deployment.get("status")
            == "ACTIVE",

        "adapter_scenario_matches":
            deployment.get("scenario")
            == SCENARIO,

        "adapter_plan_sha_matches":
            deployment.get("plan_sha256")
            == replay.get(
                "adapter_plan_sha256"
            ),

        "replay_linked_audit_exists":
            event is not None,

        "audit_created_after_replay":
            event_is_fresh,

        "old_tool_preserved":
            bool(
                event
                and event.get("old_tool")
                == "lookup_shipment"
            ),

        "native_v2_response_observed":
            bool(
                event
                and event.get(
                    "raw_v2_response", {}
                ).get(
                    "result", {}
                ).get("state")
                == "in_transit"
            ),

        "v1_response_reconstructed":
            bool(
                event
                and event.get(
                    "reconstructed_v1_response"
                )
                == expected_v1
            ),

        "victim_listed_tools":
            "ListToolsRequest"
            in transcript,

        "victim_called_tool":
            "CallToolRequest"
            in transcript,

        "victim_reported_success":
            (
                "SHIPMENT_OK"
                in transcript
                and "TRACK-7001"
                in transcript
                and "Northstar Parcel"
                in transcript
                and "2026-08-14"
                in transcript
            ),

        "contract_break_disappeared":
            "SHIPMENT_CONTRACT_BROKEN"
            not in transcript,

        "no_quota_failure":
            "RESOURCE_EXHAUSTED"
            not in transcript,

        "no_traceback":
            "Traceback (most recent call last)"
            not in transcript,

        "victim_source_unchanged":
            victim.returncode == 0,
    }

    verified = all(
        checks.values()
    )

    result = {
        "scenario": SCENARIO,
        "replay_id":
            replay["replay_id"],

        "mission_completed":
            verified,

        "failure_class":
            "OUTPUT_CONTRACT_DRIFT",

        "before":
            "CAPABILITY_LOST",

        "after": (
            "CAPABILITY_RESTORED"
            if verified
            else "VERIFICATION_FAILED"
        ),

        "victim_source_changed":
            not checks[
                "victim_source_unchanged"
            ],

        "checks":
            checks,

        "audit_event":
            event,
    }

    output = (
        SCENARIO_DIR
        / "mission-verification.json"
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
            "SHIPMENT MISSION NOT VERIFIED."
        )

    print()
    print("================================")
    print("MISSION COMPLETED AND VERIFIED.")
    print("OUTPUT CAPABILITY RESTORED.")
    print("VICTIM SOURCE CHANGED: 0 BYTES.")
    print("================================")


if __name__ == "__main__":
    main()
