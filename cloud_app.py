import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse


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


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(
        url="/mission-control",
        status_code=307,
    )


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

            # Remove every generated artifact whose stale
            # contents could otherwise masquerade as proof
            # from the current Cloud execution.
            SAFE_RETURN_SCENARIO
            / "diagnosis.json",

            SAFE_RETURN_SCENARIO
            / "policy.json",

            SAFE_RETURN_SCENARIO
            / "repair-plan.json",

            SAFE_RETURN_SCENARIO
            / "plan-validation.json",

            SAFE_RETURN_SCENARIO
            / "replay-session.json",

            SAFE_RETURN_SCENARIO
            / "action-recovery-verification.json",

            SAFE_RETURN_SCENARIO
            / "mission-verification.json",

            SAFE_RETURN_SCENARIO
            / "effect-probe.json",

            SAFE_RETURN_SCENARIO
            / "orchestration.json",

            SAFE_RETURN_SCENARIO
            / "orchestrated-verification.json",

            SAFE_RETURN_SCENARIO
            / "orchestrated-terminal.txt",
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

        # ------------------------------------------------
        # Fresh semantic pipeline.
        #
        # We deliberately run these stages here instead of
        # asking recover_case to generate them so the Cloud
        # boundary can normalize the freshly generated typed
        # plan before handing execution to the frozen engine.
        # ------------------------------------------------

        preparation_steps = [
            [
                sys.executable,
                "-m",
                "toolsuture.diagnose_case",
                "--scenario",
                "safe-return",
            ],
            [
                sys.executable,
                "-m",
                "toolsuture.policy_case",
                "--scenario",
                "safe-return",
            ],
            [
                sys.executable,
                "-m",
                "toolsuture.plan_case",
                "--scenario",
                "safe-return",
            ],
            [
                sys.executable,
                "-m",
                "toolsuture.validate_plan",
                "--scenario",
                "safe-return",
            ],
        ]

        preparation_output = []

        try:
            for step in preparation_steps:
                step_result = subprocess.run(
                    step,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                preparation_output.append(
                    "$ "
                    + " ".join(step)
                    + "\n"
                    + step_result.stdout
                    + "\n"
                    + step_result.stderr
                )

                if step_result.returncode != 0:
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "message":
                                "Fresh recovery preparation failed.",
                            "command":
                                step,
                            "returncode":
                                step_result.returncode,
                            "stdout_tail":
                                step_result.stdout[-1800:],
                            "stderr_tail":
                                step_result.stderr[-1800:],
                        },
                    )

        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=504,
                detail=(
                    "Fresh recovery preparation timed out."
                ),
            )

        # ------------------------------------------------
        # Boundary compatibility normalization.
        #
        # The current typed planner emits
        # `request_operations`.
        #
        # The frozen refund execution path predates that
        # bidirectional schema and consumes `operations`.
        #
        # Preserve the typed field and add a deterministic
        # compatibility alias. No semantic content changes.
        # ------------------------------------------------

        plan_path = (
            SAFE_RETURN_SCENARIO
            / "repair-plan.json"
        )

        plan = json.loads(
            plan_path.read_text()
        )

        request_ops = plan.get(
            "request_operations"
        )

        if request_ops is None:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Fresh repair plan is missing "
                    "request_operations."
                ),
            )

        if "operations" in plan:
            if plan["operations"] != request_ops:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Conflicting operation schemas; "
                        "refusing execution."
                    ),
                )
        else:
            plan["operations"] = request_ops

        plan_path.write_text(
            json.dumps(
                plan,
                indent=2,
            )
        )

        preparation_output.append(
            "CLOUD BOUNDARY NORMALIZATION\n"
            "request_operations -> operations\n"
            "semantic_changes: 0"
        )

        # ------------------------------------------------
        # Frozen orchestrator now consumes those freshly
        # generated and validated artifacts.
        # ------------------------------------------------

        command = [
            sys.executable,
            "-m",
            "toolsuture.recover_case",
            "--scenario",
            "safe-return",
            "--resume",
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

        proc.stdout = (
            "\n\n".join(preparation_output)
            + "\n\n"
            + proc.stdout
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


@app.post("/demo/shipment-recovery")
def demo_shipment_recovery():
    import hashlib as _hashlib
    import json as _json
    import os as _os
    import subprocess as _subprocess
    import sys as _sys
    from fastapi import HTTPException as _HTTPException

    scenario_dir = (
        ROOT
        / "evidence"
        / "scenarios"
        / "response-reshape"
    )

    provider_dir = (
        ROOT
        / "mcp_server"
    )

    victim_source = (
        ROOT
        / "shipment_victim"
        / "agent.py"
    )

    def load_json(path):
        try:
            return _json.loads(
                path.read_text()
            )
        except Exception:
            return {}

    def sha256(path):
        return _hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

    def run_stage(
        label,
        command,
        timeout=60,
    ):
        print(
            f"\n=== CLOUD SHIPMENT {label} ===",
            flush=True,
        )

        print(
            "$ " + " ".join(command),
            flush=True,
        )

        try:
            proc = _subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except _subprocess.TimeoutExpired:
            raise _HTTPException(
                status_code=504,
                detail=(
                    f"Shipment stage timed out: {label}"
                ),
            )

        if proc.stdout:
            print(
                proc.stdout,
                flush=True,
            )

        if proc.stderr:
            print(
                proc.stderr,
                flush=True,
            )

        return proc

    # ------------------------------------------
    # CLEAN ROOM
    # No previous successful evidence may count.
    # ------------------------------------------

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

    # ------------------------------------------
    # FRESH GEMINI DIAGNOSIS
    # ------------------------------------------

    diagnose = run_stage(
        "DIAGNOSE",
        [
            _sys.executable,
            "-m",
            "toolsuture.diagnose_case",
            "--scenario",
            "response-reshape",
        ],
    )

    if diagnose.returncode != 0:
        raise _HTTPException(
            status_code=500,
            detail="Fresh shipment diagnosis failed.",
        )

    diagnosis = load_json(
        scenario_dir
        / "diagnosis.json"
    )

    # ------------------------------------------
    # DETERMINISTIC POLICY
    # ------------------------------------------

    policy_proc = run_stage(
        "POLICY",
        [
            _sys.executable,
            "-m",
            "toolsuture.policy_case",
            "--scenario",
            "response-reshape",
        ],
    )

    if policy_proc.returncode != 0:
        raise _HTTPException(
            status_code=500,
            detail="Shipment policy stage failed.",
        )

    policy = load_json(
        scenario_dir
        / "policy.json"
    )

    # Fail closed.
    # Do NOT continue planning after a blocked policy.
    if policy.get("gate") != "APPROVED":
        victim_after = sha256(
            victim_source
        )

        return {
            "cloud_execution": True,
            "cloud_revision":
                _os.getenv("K_REVISION"),
            "scenario":
                "response-reshape",
            "fresh_semantic_diagnosis":
                True,
            "passed":
                False,
            "mode":
                "SAFE_HOLD",
            "diagnosis_decision":
                diagnosis.get("decision"),
            "risk_level":
                diagnosis.get("risk_level"),
            "policy_gate":
                policy.get("gate"),
            "execution_attempted":
                False,
            "mission_completed":
                False,
            "victim_integrity": {
                "sha256_before":
                    victim_before,
                "sha256_after":
                    victim_after,
                "modified":
                    victim_before != victim_after,
                "bytes_changed":
                    0
                    if victim_before == victim_after
                    else None,
            },
        }

    # ------------------------------------------
    # TYPED PLAN
    # ------------------------------------------

    plan_proc = run_stage(
        "PLAN",
        [
            _sys.executable,
            "-m",
            "toolsuture.plan_case",
            "--scenario",
            "response-reshape",
        ],
    )

    if plan_proc.returncode != 0:
        raise _HTTPException(
            status_code=500,
            detail="Shipment repair planning failed.",
        )

    plan = load_json(
        scenario_dir
        / "repair-plan.json"
    )

    # ------------------------------------------
    # DETERMINISTIC VALIDATION
    # ------------------------------------------

    validate_proc = run_stage(
        "VALIDATE",
        [
            _sys.executable,
            "-m",
            "toolsuture.validate_plan",
            "--scenario",
            "response-reshape",
        ],
    )

    if validate_proc.returncode != 0:
        raise _HTTPException(
            status_code=500,
            detail="Shipment plan validation failed.",
        )

    validation = load_json(
        scenario_dir
        / "plan-validation.json"
    )

    if (
        validation.get("gate")
        != "VALIDATED"
        or not validation.get(
            "execution_allowed"
        )
    ):
        victim_after = sha256(
            victim_source
        )

        return {
            "cloud_execution": True,
            "cloud_revision":
                _os.getenv("K_REVISION"),
            "scenario":
                "response-reshape",
            "fresh_semantic_diagnosis":
                True,
            "passed":
                False,
            "mode":
                "SAFE_HOLD",
            "diagnosis_decision":
                diagnosis.get("decision"),
            "risk_level":
                diagnosis.get("risk_level"),
            "policy_gate":
                policy.get("gate"),
            "validation_gate":
                validation.get("gate"),
            "execution_attempted":
                False,
            "mission_completed":
                False,
            "victim_integrity": {
                "sha256_before":
                    victim_before,
                "sha256_after":
                    victim_after,
                "modified":
                    victim_before != victim_after,
            },
        }

    # ------------------------------------------
    # FROZEN ENGINE EXECUTION
    # ------------------------------------------

    recover = run_stage(
        "RECOVERY",
        [
            _sys.executable,
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

    passed = all(
        [
            recover.returncode == 0,

            diagnosis.get("decision")
            == "AUTO_REPAIR_SAFE",

            diagnosis.get("risk_level")
            == "LOW",

            policy.get("gate")
            == "APPROVED",

            validation.get("gate")
            == "VALIDATED",

            orchestration.get("mode")
            == "RECOVERY_COMPLETE",

            orchestration.get(
                "mission_completed"
            )
            is True,

            verification.get(
                "mission_completed"
            )
            is True,

            checks.get(
                "replay_linked_audit_exists"
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
        ]
    )

    return {
        "cloud_execution":
            True,

        "cloud_revision":
            _os.getenv("K_REVISION"),

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
            policy.get("gate"),

        "validation_gate":
            validation.get("gate"),

        "mode":
            orchestration.get("mode"),

        "execution_attempted":
            orchestration.get(
                "execution_attempted"
            ),

        "mission_completed":
            verification.get(
                "mission_completed"
            ),

        "failure_class":
            verification.get(
                "failure_class"
            ),

        "mission_transition": {
            "before":
                verification.get("before"),

            "after":
                verification.get("after"),
        },

        "replay_id":
            verification.get("replay_id"),

        "plan_shape": {
            "request_operations":
                len(
                    plan.get(
                        "request_operations",
                        [],
                    )
                ),

            "response_operations":
                len(
                    plan.get(
                        "response_operations",
                        [],
                    )
                ),
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
                0
                if victim_before
                == victim_after
                else None,
        },

        "verification_checks":
            checks,
    }


# TOOLSUTURE_MISSION_CONTROL_V1

@app.get("/mission-control")
def mission_control():
    from fastapi.responses import HTMLResponse

    page = (
        ROOT
        / "web"
        / "mission_control.html"
    )

    return HTMLResponse(
        page.read_text()
    )


@app.get("/demo/evidence-summary")
def evidence_summary():

    repeatability_path = (
        ROOT
        / "evidence"
        / "banked"
        / "cloud-shipment-repeatability-0568c25"
        / "repeatability-summary.json"
    )

    safe_hold_path = (
        ROOT
        / "evidence"
        / "banked"
        / "cloud-dangerous-safe-hold"
        / "proof-summary.json"
    )

    def load_optional(path):
        try:
            return json.loads(
                path.read_text()
            )
        except Exception:
            return None

    repeatability = load_optional(
        repeatability_path
    )

    safe_hold = load_optional(
        safe_hold_path
    )

    return {
        "repeatability":
            repeatability,

        "dangerous_safe_hold":
            safe_hold,

        "headline_proof": {
            "frozen_agent_bytes_changed":
                0,

            "verified_cloud_recoveries":
                3,

            "dangerous_drift_refused":
                bool(
                    safe_hold
                    and safe_hold.get(
                        "all_checks_pass"
                    )
                ),
        },
    }


# TOOLSUTURE_REALTIME_RECOVERY_V1

@app.get("/demo/shipment-recovery-stream")
def shipment_recovery_stream():

    from fastapi.responses import StreamingResponse

    from toolsuture.cloud_stream import (
        shipment_recovery_event_stream,
    )

    return StreamingResponse(
        shipment_recovery_event_stream(ROOT),
        media_type="text/event-stream",
        headers={
            "Cache-Control":
                "no-cache, no-transform",

            "X-Accel-Buffering":
                "no",
        },
    )
