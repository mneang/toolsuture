import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    scenario_dir = ROOT / "evidence" / "scenarios" / args.scenario
    records = ROOT / "mcp_server" / ".refund_records.json"
    deployment_path = ROOT / "mcp_server" / ".deployed_adapter.json"

    if records.exists():
        records.unlink()

    deployment = json.loads(deployment_path.read_text())

    victim = subprocess.run(
        ["sha256sum", "-c", "victim_agent.sha256"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if victim.returncode != 0:
        raise SystemExit("STOP: frozen victim integrity failed.")

    marker = {
        "scenario": args.scenario,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "provider_version": (
            ROOT / "mcp_server" / ".provider_version"
        ).read_text().strip(),
        "adapter_plan_sha256": deployment["plan_sha256"],
        "victim_integrity": "PASS",
    }

    path = scenario_dir / "replay-session.json"
    path.write_text(json.dumps(marker, indent=2))

    print(json.dumps(marker, indent=2))
    print()
    print("Provider records cleared.")
    print("Replay session armed.")
    print("Next successful provider record must come AFTER this marker.")


if __name__ == "__main__":
    main()
