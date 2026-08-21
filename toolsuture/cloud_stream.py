import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def sse(payload: dict) -> str:
    return (
        "data: "
        + json.dumps(
            payload,
            separators=(",", ":"),
        )
        + "\n\n"
    )


def load_json(path: Path) -> dict:
    try:
        return json.loads(
            path.read_text()
        )
    except Exception:
        return {}


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def run_stage(
    root: Path,
    label: str,
    command: list[str],
    timeout: int = 60,
):
    print(
        f"\n=== STREAM {label} ===",
        flush=True,
    )

    print(
        "$ " + " ".join(command),
        flush=True,
    )

    process = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if process.stdout:
        print(
            process.stdout,
            flush=True,
        )

    if process.stderr:
        print(
            process.stderr,
            flush=True,
        )

    return process


def shipment_recovery_event_stream(
    root: Path,
):
    """
    Real Cloud execution events for the already-proven
    response-reshape recovery path.

    IMPORTANT:
    - does not modify frozen engine files
    - does not modify frozen victim files
    - emits stage completion only after the corresponding
      backend stage has actually returned
    """

    scenario_dir = (
        root
        / "evidence"
        / "scenarios"
        / "response-reshape"
    )

    provider_dir = (
        root
        / "mcp_server"
    )

    victim_source = (
        root
        / "shipment_victim"
        / "agent.py"
    )

    try:
        # ----------------------------------------------------
        # CONNECT
        # ----------------------------------------------------

        yield ": connected\n\n"

        yield sse({
            "type": "stream",
            "status": "connected",
        })

        # ----------------------------------------------------
        # CLEAN ROOM / OBSERVE
        # ----------------------------------------------------

        stale_files = [
            scenario_dir / "diagnosis.json",
            scenario_dir / "policy.json",
            scenario_dir / "repair-plan.json",
            scenario_dir / "plan-validation.json",
            scenario_dir / "replay-session.json",
            scenario_dir / "mission-verification.json",
            scenario_dir / "orchestration.json",
            scenario_dir / "orchestrated-terminal.txt",
            scenario_dir / "orchestrated-verification.json",
            scenario_dir / "effect-probe.json",

            provider_dir
            / ".shipment_adapter_audit.jsonl",

            provider_dir
            / ".shipment_replay_context.json",

            provider_dir
            / ".deployed_adapter.json",
        ]

        yield sse({
            "type": "stage",
            "stage": "observe",
            "status": "started",
            "value": "Inspecting contract drift",
        })

        for path in stale_files:
            if path.exists():
                path.unlink()

        (
            provider_dir
            / ".shipment_provider_version"
        ).write_text("v2")

        victim_before = sha256(
            victim_source
        )

        yield sse({
            "type": "stage",
            "stage": "observe",
            "status": "complete",
            "value": "OUTPUT_CONTRACT_DRIFT",
        })

        # ----------------------------------------------------
        # FRESH GEMINI DIAGNOSIS
        # ----------------------------------------------------

        yield sse({
            "type": "stage",
            "stage": "diagnose",
            "status": "started",
            "value": "Gemini reasoning",
        })

        diagnose = run_stage(
            root,
            "DIAGNOSE",
            [
                sys.executable,
                "-m",
                "toolsuture.diagnose_case",
                "--scenario",
                "response-reshape",
            ],
        )

        if diagnose.returncode != 0:
            raise RuntimeError(
                "Fresh semantic diagnosis failed."
            )

        diagnosis = load_json(
            scenario_dir
            / "diagnosis.json"
        )

        yield sse({
            "type": "stage",
            "stage": "diagnose",
            "status": "complete",
            "value": (
                f"{diagnosis.get('decision')} · "
                f"{diagnosis.get('risk_level')}"
            ),
            "decision":
                diagnosis.get("decision"),
            "risk_level":
                diagnosis.get("risk_level"),
        })

        # ----------------------------------------------------
        # DETERMINISTIC POLICY
        # ----------------------------------------------------

        yield sse({
            "type": "stage",
            "stage": "policy",
            "status": "started",
            "value": "Evaluating safety gate",
        })

        policy_proc = run_stage(
            root,
            "POLICY",
            [
                sys.executable,
                "-m",
                "toolsuture.policy_case",
                "--scenario",
                "response-reshape",
            ],
        )

        if policy_proc.returncode != 0:
            raise RuntimeError(
                "Policy stage failed."
            )

        policy = load_json(
            scenario_dir
            / "policy.json"
        )

        policy_gate = policy.get(
            "gate"
        )

        yield sse({
            "type": "stage",
            "stage": "policy",
            "status": (
                "complete"
                if policy_gate == "APPROVED"
                else "blocked"
            ),
            "value": policy_gate,
        })

        # Fail closed.
        if policy_gate != "APPROVED":

            victim_after = sha256(
                victim_source
            )

            result = {
                "cloud_execution": True,
                "scenario": "response-reshape",
                "fresh_semantic_diagnosis": True,
                "passed": False,
                "mode": "SAFE_HOLD",
                "diagnosis_decision":
                    diagnosis.get("decision"),
                "risk_level":
                    diagnosis.get("risk_level"),
                "policy_gate":
                    policy_gate,
                "execution_attempted": False,
                "mission_completed": False,
                "victim_integrity": {
                    "sha256_before":
                        victim_before,
                    "sha256_after":
                        victim_after,
                    "modified":
                        victim_before
                        != victim_after,
                    "bytes_changed":
                        (
                            0
                            if victim_before
                            == victim_after
                            else None
                        ),
                },
            }

            yield sse({
                "type": "result",
                "data": result,
            })

            return

        # ----------------------------------------------------
        # TYPED REPAIR PLAN
        # ----------------------------------------------------

        yield sse({
            "type": "stage",
            "stage": "plan",
            "status": "started",
            "value": "Building typed repair",
        })

        plan_proc = run_stage(
            root,
            "PLAN",
            [
                sys.executable,
                "-m",
                "toolsuture.plan_case",
                "--scenario",
                "response-reshape",
            ],
        )

        if plan_proc.returncode != 0:
            raise RuntimeError(
                "Repair planning failed."
            )

        plan = load_json(
            scenario_dir
            / "repair-plan.json"
        )

        request_count = len(
            plan.get(
                "request_operations",
                [],
            )
        )

        response_count = len(
            plan.get(
                "response_operations",
                [],
            )
        )

        yield sse({
            "type": "stage",
            "stage": "plan",
            "status": "complete",
            "value": (
                f"{request_count} request · "
                f"{response_count} response"
            ),
            "request_operations":
                request_count,
            "response_operations":
                response_count,
        })

        # ----------------------------------------------------
        # DETERMINISTIC PLAN VALIDATION
        # ----------------------------------------------------

        yield sse({
            "type": "stage",
            "stage": "validate",
            "status": "started",
            "value": "Deterministic validation",
        })

        validate_proc = run_stage(
            root,
            "VALIDATE",
            [
                sys.executable,
                "-m",
                "toolsuture.validate_plan",
                "--scenario",
                "response-reshape",
            ],
        )

        if validate_proc.returncode != 0:
            raise RuntimeError(
                "Plan validation failed."
            )

        validation = load_json(
            scenario_dir
            / "plan-validation.json"
        )

        validation_gate = (
            validation.get("gate")
        )

        execution_allowed = (
            validation.get(
                "execution_allowed"
            )
        )

        yield sse({
            "type": "stage",
            "stage": "validate",
            "status": (
                "complete"
                if (
                    validation_gate
                    == "VALIDATED"
                    and execution_allowed
                )
                else "blocked"
            ),
            "value":
                validation_gate,
        })

        if (
            validation_gate
            != "VALIDATED"
            or not execution_allowed
        ):
            raise RuntimeError(
                "Validated execution was not allowed."
            )

        # ----------------------------------------------------
        # FROZEN ORCHESTRATOR / REPLAY
        # ----------------------------------------------------

        yield sse({
            "type": "stage",
            "stage": "replay",
            "status": "started",
            "value": "Replaying frozen agent",
        })

        recover = run_stage(
            root,
            "RECOVERY",
            [
                sys.executable,
                "-m",
                "toolsuture.recover_case",
                "--scenario",
                "response-reshape",
                "--resume",
                "--execute",
            ],
            timeout=120,
        )

        orchestration = load_json(
            scenario_dir
            / "orchestration.json"
        )

        verification = load_json(
            scenario_dir
            / "mission-verification.json"
        )

        victim_after = sha256(
            victim_source
        )

        checks = (
            verification.get("checks")
            or {}
        )

        audit = (
            verification.get("audit_event")
            or {}
        )

        if recover.returncode != 0:
            raise RuntimeError(
                "Frozen agent recovery failed."
            )

        yield sse({
            "type": "stage",
            "stage": "replay",
            "status": "complete",
            "value": (
                orchestration.get("mode")
                or "RECOVERY_RETURNED"
            ),
        })

        # ----------------------------------------------------
        # INDEPENDENT VERIFICATION
        #
        # verify_shipment_recovery executes inside the frozen
        # orchestrator above. This event is emitted only after
        # its current replay-linked proof exists and is loaded.
        # ----------------------------------------------------

        yield sse({
            "type": "stage",
            "stage": "verify",
            "status": "started",
            "value": "Checking replay-linked proof",
        })

        transition_before = (
            verification.get("before")
        )

        transition_after = (
            verification.get("after")
        )

        mission_completed = (
            verification.get(
                "mission_completed"
            )
            is True
        )

        yield sse({
            "type": "stage",
            "stage": "verify",
            "status": (
                "complete"
                if mission_completed
                else "blocked"
            ),
            "value": (
                "MISSION VERIFIED"
                if mission_completed
                else "VERIFICATION FAILED"
            ),
        })

        # ----------------------------------------------------
        # FINAL VERIFIED RESULT
        # ----------------------------------------------------

        passed = all([
            diagnosis.get("decision")
            == "AUTO_REPAIR_SAFE",

            diagnosis.get("risk_level")
            == "LOW",

            policy_gate
            == "APPROVED",

            validation_gate
            == "VALIDATED",

            orchestration.get("mode")
            == "RECOVERY_COMPLETE",

            orchestration.get(
                "mission_completed"
            )
            is True,

            mission_completed,

            transition_before
            == "CAPABILITY_LOST",

            transition_after
            == "CAPABILITY_RESTORED",

            checks.get(
                "replay_linked_audit_exists"
            )
            is True,

            checks.get(
                "audit_created_after_replay"
            )
            is True,

            checks.get(
                "native_v2_response_observed"
            )
            is True,

            checks.get(
                "v1_response_reconstructed"
            )
            is True,

            checks.get(
                "victim_reported_success"
            )
            is True,

            victim_before
            == victim_after,
        ])

        result = {
            "cloud_execution":
                True,

            "cloud_revision":
                os.getenv("K_REVISION"),

            "scenario":
                "response-reshape",

            "fresh_semantic_diagnosis":
                True,

            "frozen_orchestrator_resume":
                True,

            "passed":
                passed,

            "diagnosis_decision":
                diagnosis.get("decision"),

            "risk_level":
                diagnosis.get("risk_level"),

            "policy_gate":
                policy_gate,

            "validation_gate":
                validation_gate,

            "mode":
                orchestration.get("mode"),

            "execution_attempted":
                orchestration.get(
                    "execution_attempted"
                ),

            "mission_completed":
                mission_completed,

            "failure_class":
                verification.get(
                    "failure_class"
                ),

            "mission_transition": {
                "before":
                    transition_before,

                "after":
                    transition_after,
            },

            "replay_id":
                verification.get(
                    "replay_id"
                ),

            "plan_shape": {
                "request_operations":
                    request_count,

                "response_operations":
                    response_count,
            },

            "response_repair": {
                "raw_v2_response":
                    audit.get(
                        "raw_v2_response"
                    ),

                "reconstructed_v1_response":
                    audit.get(
                        "reconstructed_v1_response"
                    ),
            },

            "victim_integrity": {
                "sha256_before":
                    victim_before,

                "sha256_after":
                    victim_after,

                "modified":
                    victim_before
                    != victim_after,

                "bytes_changed":
                    (
                        0
                        if victim_before
                        == victim_after
                        else None
                    ),
            },

            "verification_checks":
                checks,
        }

        yield sse({
            "type": "result",
            "data": result,
        })

    except Exception as exc:

        print(
            "STREAM ERROR:",
            repr(exc),
            flush=True,
        )

        yield sse({
            "type": "error",
            "message": str(exc),
        })
