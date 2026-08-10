import argparse
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    scenario_dir = (
        ROOT / "evidence" / "scenarios" / args.scenario
    )

    records_path = (
        ROOT / "mcp_server" / ".refund_records.json"
    )

    audit_path = (
        ROOT / "mcp_server" / ".adapter_audit.jsonl"
    )

    context_path = (
        ROOT / "mcp_server" / ".replay_context.json"
    )

    deployment = json.loads(
        (
            ROOT
            / "mcp_server"
            / ".deployed_adapter.json"
        ).read_text()
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

    if victim.returncode != 0:
        raise SystemExit(
            "STOP: frozen victim integrity failed."
        )

    # Remove evidence from previous canaries/replays.
    for path in (
        records_path,
        audit_path,
        context_path,
    ):
        if path.exists():
            path.unlink()

    replay_id = str(uuid.uuid4())
    started_at = datetime.now(
        timezone.utc
    ).isoformat()

    context = {
        "replay_id": replay_id,
        "scenario": args.scenario,
        "started_at": started_at,
    }

    context_path.write_text(
        json.dumps(context, indent=2)
    )

    marker = {
        "scenario": args.scenario,
        "replay_id": replay_id,
        "started_at": started_at,
        "provider_version": (
            ROOT
            / "mcp_server"
            / ".provider_version"
        ).read_text().strip(),
        "adapter_plan_sha256":
            deployment["plan_sha256"],
        "victim_integrity": "PASS",
    }

    output = (
        scenario_dir
        / "replay-session.json"
    )

    output.write_text(
        json.dumps(marker, indent=2)
    )

    print(json.dumps(marker, indent=2))
    print()
    print("Old runtime evidence cleared.")
    print("Replay session armed.")
    print(
        "Only adapter calls carrying this replay_id "
        "can satisfy verification."
    )


if __name__ == "__main__":
    main()
