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
