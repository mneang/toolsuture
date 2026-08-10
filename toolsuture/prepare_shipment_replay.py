import json
import subprocess
import uuid
from datetime import datetime, timezone
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

CONTEXT_FILE = (
    ROOT
    / "mcp_server"
    / ".shipment_replay_context.json"
)

VERSION_FILE = (
    ROOT
    / "mcp_server"
    / ".shipment_provider_version"
)

DEPLOYMENT_FILE = (
    ROOT
    / "mcp_server"
    / ".deployed_adapter.json"
)


def main():
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

    if victim.returncode != 0:
        raise SystemExit(
            "STOP: shipment victim integrity failed."
        )

    provider_version = (
        VERSION_FILE.read_text().strip()
    )

    if provider_version != "v2":
        raise SystemExit(
            "STOP: shipment provider is not v2."
        )

    deployment = json.loads(
        DEPLOYMENT_FILE.read_text()
    )

    if (
        deployment.get("status") != "ACTIVE"
        or deployment.get("scenario")
        != SCENARIO
    ):
        raise SystemExit(
            "STOP: response-reshape adapter "
            "is not ACTIVE."
        )

    if AUDIT_FILE.exists():
        AUDIT_FILE.unlink()

    if CONTEXT_FILE.exists():
        CONTEXT_FILE.unlink()

    replay_id = str(uuid.uuid4())

    started_at = datetime.now(
        timezone.utc
    ).isoformat()

    context = {
        "replay_id": replay_id,
        "scenario": SCENARIO,
        "started_at": started_at,
    }

    CONTEXT_FILE.write_text(
        json.dumps(
            context,
            indent=2,
        )
    )

    session = {
        "scenario": SCENARIO,
        "replay_id": replay_id,
        "started_at": started_at,
        "provider_version":
            provider_version,
        "adapter_plan_sha256":
            deployment["plan_sha256"],
        "victim_integrity": "PASS",
    }

    output = (
        SCENARIO_DIR
        / "replay-session.json"
    )

    output.write_text(
        json.dumps(
            session,
            indent=2,
        )
    )

    print(
        json.dumps(
            session,
            indent=2,
        )
    )

    print()
    print("Shipment replay armed.")
    print(
        "Only audit events carrying this "
        "replay_id can satisfy verification."
    )


if __name__ == "__main__":
    main()
