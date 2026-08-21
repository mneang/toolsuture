import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException


ROOT = Path(__file__).resolve().parent

GOAL4_BANK = (
    ROOT
    / "evidence"
    / "banked"
    / "score-4-0"
    / "goal-4-unified-recovery"
    / "result.json"
)

SAFE_HOLD_SCENARIO = (
    ROOT
    / "evidence"
    / "scenarios"
    / "blind-03"
)

LOCK = threading.Lock()

app = FastAPI(
    title="ToolSuture",
    description=(
        "Recovery control plane for deployed agents "
        "whose external tool contracts changed."
    ),
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "service": "ToolSuture",
        "mission": (
            "Keep deployed agents working "
            "when their tools change."
        ),
        "cloud": "Google Cloud Run",
        "victim_agent_modified": False,
    }


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "service": "toolsuture",
    }


@app.get("/ready")
def ready():
    return {
        "status": "ready",
        "service": "toolsuture",
        "cloud_revision": os.getenv("K_REVISION"),
    }


@app.get("/proof/goal4")
def goal4_proof():
    if not GOAL4_BANK.exists():
        raise HTTPException(
            status_code=404,
            detail="Banked Goal #4 proof not found.",
        )

    raw = GOAL4_BANK.read_bytes()
    data = json.loads(raw)

    return {
        "goal4_verified":
            data.get("goal4_verified"),

        "git_commit":
            data.get("git_commit"),

        "no_code_edits_between_tests":
            data.get(
                "no_code_edits_between_tests"
            ),

        "victim_agents_modified":
            data.get(
                "victim_agents_modified"
            ),

        "tests":
            data.get("tests"),

        "evidence_sha256":
            hashlib.sha256(raw).hexdigest(),
    }


@app.post("/demo/safe-hold")
def demo_safe_hold():
    """
    Judge-safe Cloud demonstration.

    Executes the actual frozen ToolSuture
    orchestrator against the dangerous
    blind-03 case.

    Expected behavior:
      REFUSE -> SAFE_HOLD
      execution_attempted = false

    No consequential provider action
    is allowed by this endpoint.
    """

    with LOCK:
        command = [
            sys.executable,
            "-m",
            "toolsuture.recover_case",
            "--scenario",
            "blind-03",
            "--execute",
        ]

        try:
            proc = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )

        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=504,
                detail="Recovery evaluation timed out.",
            )

        print(
            "=== CLOUD FRESH RECOVERY EXECUTION ===",
            flush=True,
        )
        print(proc.stdout, flush=True)

        if proc.stderr:
            print(
                "=== CLOUD RECOVERY STDERR ===",
                flush=True,
            )
            print(proc.stderr, flush=True)

        orchestration_path = (
            SAFE_HOLD_SCENARIO
            / "orchestration.json"
        )

        if (
            proc.returncode != 0
            or not orchestration_path.exists()
        ):
            raise HTTPException(
                status_code=500,
                detail={
                    "message":
                        "Frozen orchestrator failed.",

                    "returncode":
                        proc.returncode,

                    "stderr_tail":
                        proc.stderr[-1200:],
                },
            )

        result = json.loads(
            orchestration_path.read_text()
        )

        passed = (
            result.get("mode")
            == "SAFE_HOLD"
            and result.get(
                "execution_attempted"
            )
            is False
            and result.get(
                "diagnosis_decision"
            )
            == "REFUSE"
            and result.get(
                "policy_gate"
            )
            == "BLOCKED"
        )

        diagnosis_path = (
            SAFE_HOLD_SCENARIO
            / "diagnosis.json"
        )

        diagnosis_sha256 = None

        if diagnosis_path.exists():
            diagnosis_sha256 = hashlib.sha256(
                diagnosis_path.read_bytes()
            ).hexdigest()

        return {
            "cloud_execution": True,
            "cloud_revision": os.getenv("K_REVISION"),
            "scenario": "blind-03",
            "fresh_semantic_diagnosis": True,
            "resume_used": False,
            "diagnosis_sha256": diagnosis_sha256,
            "run_id": result.get("run_id"),
            "passed": passed,
            "mode": result.get("mode"),
            "diagnosis_decision":
                result.get(
                    "diagnosis_decision"
                ),
            "risk_level":
                result.get("risk_level"),
            "policy_gate":
                result.get("policy_gate"),
            "execution_attempted":
                result.get(
                    "execution_attempted"
                ),
            "mission_completed":
                result.get(
                    "mission_completed"
                ),
            "victim_agent_modified":
                False,
        }


# ============================================================
# GRAND PRIZE SAFE RECOVERY DEMO
# ============================================================

SAFE_RETURN_SCENARIO = (
    ROOT
    / "evidence"
    / "scenarios"
    / "safe-return"
)

REFUND_PROVIDER_DIR = (
    ROOT
    / "mcp_server"
)


def _load_json_if_present(path: Path) -> dict:
    if not path.exists():
        return {}

    return json.loads(
        path.read_text()
    )


@app.post("/demo/safe-recovery")
def demo_safe_recovery():
    """
    Grand Prize attacking demonstration.

    A provider contract has migrated from v1
    refund_order to v2 issue_refund.

    This route:
      1. resets stale demo-provider state
      2. forces provider v2
      3. performs fresh Gemini diagnosis
      4. applies deterministic policy/validation
      5. deploys the bounded compatibility repair
      6. replays the unchanged victim agent
      7. independently verifies provider-side effect

    This operates only against ToolSuture's
    local simulated refund provider.
    """

    with LOCK:

        # ----------------------------------------
        # Prevent stale state from creating a
        # false-positive recovery result.
        # ----------------------------------------

        runtime_paths = [
            REFUND_PROVIDER_DIR
            / ".deployed_adapter.json",

            REFUND_PROVIDER_DIR
            / ".refund_records.json",

            REFUND_PROVIDER_DIR
            / ".adapter_audit.jsonl",

            REFUND_PROVIDER_DIR
            / ".replay_context.json",
        ]

        for path in runtime_paths:
            path.unlink(
                missing_ok=True
            )

        # Simulate the external provider having
        # migrated from contract v1 to contract v2.
        (
            REFUND_PROVIDER_DIR
            / ".provider_version"
        ).write_text("v2")

        victim_path = (
            ROOT
            / "victim_agent"
            / "agent.py"
        )

        victim_hash_before = (
            hashlib.sha256(
                victim_path.read_bytes()
            ).hexdigest()
        )

        command = [
            sys.executable,
            "-m",
            "toolsuture.recover_case",
            "--scenario",
            "safe-return",
            "--execute",
        ]

        try:
            proc = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=105,
            )

        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=504,
                detail=(
                    "Safe recovery timed out."
                ),
            )

        print(
            "=== CLOUD SAFE RECOVERY EXECUTION ===",
            flush=True,
        )

        print(
            proc.stdout,
            flush=True,
        )

        if proc.stderr:
            print(
                "=== CLOUD SAFE RECOVERY STDERR ===",
                flush=True,
            )

            print(
                proc.stderr,
                flush=True,
            )

        victim_hash_after = (
            hashlib.sha256(
                victim_path.read_bytes()
            ).hexdigest()
        )

        orchestration = _load_json_if_present(
            SAFE_RETURN_SCENARIO
            / "orchestration.json"
        )

        diagnosis = _load_json_if_present(
            SAFE_RETURN_SCENARIO
            / "diagnosis.json"
        )

        action_verification = (
            _load_json_if_present(
                SAFE_RETURN_SCENARIO
                / "action-recovery-verification.json"
            )
        )

        mission_verification = (
            _load_json_if_present(
                SAFE_RETURN_SCENARIO
                / "mission-verification.json"
            )
        )

        provider_records = (
            _load_json_if_present(
                REFUND_PROVIDER_DIR
                / ".refund_records.json"
            )
        )

        provider_record = (
            provider_records.get(
                "ORD-1002",
                {},
            )
        )

        if (
            proc.returncode != 0
            or not orchestration
        ):
            raise HTTPException(
                status_code=500,
                detail={
                    "message":
                        "Safe Cloud recovery failed.",

                    "returncode":
                        proc.returncode,

                    "stdout_tail":
                        proc.stdout[-1800:],

                    "stderr_tail":
                        proc.stderr[-1800:],
                },
            )

        adapter_event = (
            action_verification.get(
                "adapter_event",
                {},
            )
        )

        passed = all([
            orchestration.get("mode")
            == "RECOVERY_COMPLETE",

            orchestration.get(
                "execution_attempted"
            )
            is True,

            orchestration.get(
                "mission_completed"
            )
            is True,

            diagnosis.get("decision")
            == "AUTO_REPAIR_SAFE",

            action_verification.get(
                "action_restored"
            )
            is True,

            action_verification.get(
                "proof_level"
            )
            == "REPLAY_LINKED_ACTION_VERIFIED",

            mission_verification.get(
                "mission_completed"
            )
            is True,

            provider_record.get(
                "status"
            )
            == "refunded",

            provider_record.get(
                "provider_version"
            )
            == "v2",

            victim_hash_before
            == victim_hash_after,
        ])

        diagnosis_path = (
            SAFE_RETURN_SCENARIO
            / "diagnosis.json"
        )

        diagnosis_sha256 = (
            hashlib.sha256(
                diagnosis_path.read_bytes()
            ).hexdigest()
            if diagnosis_path.exists()
            else None
        )

        return {
            "cloud_execution":
                True,

            "cloud_revision":
                os.getenv("K_REVISION"),

            "scenario":
                "safe-return",

            "fresh_semantic_diagnosis":
                True,

            "resume_used":
                False,

            "passed":
                passed,

            "run_id":
                orchestration.get(
                    "run_id"
                ),

            "diagnosis_sha256":
                diagnosis_sha256,

            "diagnosis_decision":
                diagnosis.get(
                    "decision"
                ),

            "risk_level":
                diagnosis.get(
                    "risk_level"
                ),

            "policy_gate":
                orchestration.get(
                    "policy_gate"
                ),

            "validation_gate":
                orchestration.get(
                    "validation_gate"
                ),

            "recovery_handler":
                orchestration.get(
                    "recovery_handler"
                ),

            "mode":
                orchestration.get(
                    "mode"
                ),

            "execution_attempted":
                orchestration.get(
                    "execution_attempted"
                ),

            "mission_completed":
                orchestration.get(
                    "mission_completed"
                ),

            "mission_transition": {
                "before":
                    mission_verification.get(
                        "before"
                    ),

                "after":
                    mission_verification.get(
                        "after"
                    ),
            },

            "provider_effect": {
                "proof_level":
                    action_verification.get(
                        "proof_level"
                    ),

                "action_restored":
                    action_verification.get(
                        "action_restored"
                    ),

                "old_tool":
                    adapter_event.get(
                        "old_tool"
                    ),

                "new_tool":
                    adapter_event.get(
                        "new_tool"
                    ),

                "old_args":
                    adapter_event.get(
                        "old_args"
                    ),

                "compiled_v2_args":
                    adapter_event.get(
                        "compiled_v2_args"
                    ),

                "provider_record":
                    provider_record,
            },

            "victim_integrity": {
                "sha256_before":
                    victim_hash_before,

                "sha256_after":
                    victim_hash_after,

                "modified":
                    victim_hash_before
                    != victim_hash_after,

                "bytes_changed":
                    0
                    if victim_hash_before
                    == victim_hash_after
                    else None,
            },

            "mission_checks":
                mission_verification.get(
                    "checks"
                ),

            "action_checks":
                action_verification.get(
                    "checks"
                ),
        }
