import argparse
import json
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from toolsuture.probe_effect import probe_scenario


ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = (
    ROOT
    / "evidence"
    / "scenarios"
)


def load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"STOP: required artifact missing: {path}"
        )

    return json.loads(
        path.read_text()
    )


def run_module(
    module: str,
    *args: str,
) -> None:
    command = [
        sys.executable,
        "-m",
        module,
        *args,
    ]

    print()
    print(
        "$",
        " ".join(command),
    )

    result = subprocess.run(
        command,
        cwd=ROOT,
    )

    if result.returncode != 0:
        raise SystemExit(
            f"STOP: {module} failed."
        )


def require_scenario_inputs(
    scenario_dir: Path,
) -> None:
    required = [
        "mission.txt",
        "old-contract.json",
        "new-contract.json",
        "provider-semantics.json",
    ]

    missing = [
        name
        for name in required
        if not (
            scenario_dir / name
        ).exists()
    ]

    if missing:
        raise SystemExit(
            "STOP: scenario inputs missing: "
            + ", ".join(missing)
        )


def write_orchestration(
    scenario_dir: Path,
    result: dict,
) -> None:
    output = (
        scenario_dir
        / "orchestration.json"
    )

    # If a final state does not explicitly carry run_id,
    # inherit the currently active run_id.
    if (
        "run_id" not in result
        and output.exists()
    ):
        try:
            current = json.loads(
                output.read_text()
            )

            if current.get("run_id"):
                result["run_id"] = (
                    current["run_id"]
                )

        except Exception:
            pass

    output.write_text(
        json.dumps(
            result,
            indent=2,
        )
    )

    run_id = result.get("run_id")

    if run_id:
        runs_dir = (
            scenario_dir
            / "runs"
        )

        runs_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        history = (
            runs_dir
            / f"{run_id}.json"
        )

        history.write_text(
            json.dumps(
                result,
                indent=2,
            )
        )

    print()

    try:
        display_path = output.relative_to(
            ROOT
        )
    except ValueError:
        display_path = output

    print(
        f"Saved -> {display_path}"
    )


ADAPTER_FILE = (
    ROOT
    / "mcp_server"
    / ".deployed_adapter.json"
)


def snapshot_deployment():
    if not ADAPTER_FILE.exists():
        return None

    return ADAPTER_FILE.read_bytes()


def restore_deployment(
    snapshot,
) -> None:
    if snapshot is None:
        if ADAPTER_FILE.exists():
            ADAPTER_FILE.unlink()

        return

    ADAPTER_FILE.write_bytes(
        snapshot
    )


def disable_current_adapter(
    reason: str,
) -> None:
    if not ADAPTER_FILE.exists():
        return

    deployment = json.loads(
        ADAPTER_FILE.read_text()
    )

    deployment["status"] = (
        "DISABLED_PENDING_VERIFICATION"
    )

    deployment[
        "disabled_reason"
    ] = reason

    deployment[
        "disabled_at"
    ] = datetime.now(
        timezone.utc
    ).isoformat()

    ADAPTER_FILE.write_text(
        json.dumps(
            deployment,
            indent=2,
        )
    )


def inspect_failed_replay(
    scenario_dir: Path,
) -> dict:
    transcript_path = (
        scenario_dir
        / "orchestrated-terminal.txt"
    )

    transcript = ""

    if transcript_path.exists():
        transcript = (
            transcript_path.read_text(
                errors="replace"
            )
        )

    if "RESOURCE_EXHAUSTED" in transcript:
        error_class = (
            "MODEL_QUOTA_EXHAUSTED"
        )

    elif (
        "Traceback (most recent call last)"
        in transcript
    ):
        error_class = (
            "REPLAY_PROCESS_FAILED"
        )

    else:
        error_class = (
            "RECOVERY_EXECUTION_FAILED"
        )

    return {
        "error_class":
            error_class,

        "tool_call_observed":
            "CallToolRequest"
            in transcript,

        "tool_list_observed":
            "ListToolsRequest"
            in transcript,

        "quota_failure_observed":
            "RESOURCE_EXHAUSTED"
            in transcript,

        "traceback_observed":
            "Traceback (most recent call last)"
            in transcript,
    }

def run_shipment_replay(
    scenario_dir: Path,
) -> dict:
    canonical_proof = (
        scenario_dir
        / "mission-verification.json"
    )

    if canonical_proof.exists():
        previous = json.loads(
            canonical_proof.read_text()
        )

        if previous.get(
            "mission_completed"
        ):
            shutil.copy2(
                canonical_proof,
                scenario_dir
                / "pre-orchestration-verified-proof.json",
            )

            print(
                "Previous verified recovery proof preserved."
            )

    run_module(
        "toolsuture.prepare_shipment_replay"
    )

    replay = load_json(
        scenario_dir
        / "replay-session.json"
    )

    mission = (
        scenario_dir
        / "mission.txt"
    ).read_text().strip()

    print()
    print("=== REPLAY ===")
    print(
        "Frozen victim: shipment_victim"
    )
    print(
        "Replay ID:",
        replay["replay_id"],
    )
    print(
        "Mission:",
        mission,
    )

    command = [
        "adk",
        "run",
        "shipment_victim",
    ]

    process = subprocess.run(
        command,
        cwd=ROOT,
        input=(
            mission
            + "\n"
            + "exit\n"
        ),
        text=True,
        capture_output=True,
    )

    transcript = (
        process.stdout
        + "\n"
        + process.stderr
    )

    transcript_path = (
        scenario_dir
        / "orchestrated-terminal.txt"
    )

    transcript_path.write_text(
        transcript
    )

    print()
    print(transcript)

    if process.returncode != 0:
        raise SystemExit(
            "STOP: frozen victim replay process failed."
        )

    run_module(
        "toolsuture.verify_shipment_recovery",
        "--terminal",
        str(
            transcript_path.relative_to(
                ROOT
            )
        ),
    )

    verification = load_json(
        canonical_proof
    )

    shutil.copy2(
        canonical_proof,
        scenario_dir
        / "orchestrated-verification.json",
    )

    if not verification.get(
        "mission_completed"
    ):
        raise SystemExit(
            "STOP: replay was not independently verified."
        )

    return {
        "replay_id":
            verification.get(
                "replay_id"
            ),

        "mission_completed":
            True,

        "after":
            verification.get(
                "after"
            ),

        "victim_source_changed":
            verification.get(
                "victim_source_changed"
            ),
    }



def run_refund_replay(
    scenario_dir: Path,
) -> dict:
    canonical_proof = (
        scenario_dir
        / "mission-verification.json"
    )

    if canonical_proof.exists():
        previous = json.loads(
            canonical_proof.read_text()
        )

        if previous.get(
            "mission_completed"
        ):
            shutil.copy2(
                canonical_proof,
                scenario_dir
                / "pre-registry-verified-proof.json",
            )

            print(
                "Previous verified refund proof preserved."
            )

    scenario = scenario_dir.name

    run_module(
        "toolsuture.prepare_replay",
        "--scenario",
        scenario,
    )

    replay = load_json(
        scenario_dir
        / "replay-session.json"
    )

    mission = (
        scenario_dir
        / "mission.txt"
    ).read_text().strip()

    print()
    print("=== REPLAY ===")
    print(
        "Frozen victim: victim_agent"
    )
    print(
        "Replay ID:",
        replay["replay_id"],
    )
    print(
        "Mission:",
        mission,
    )

    command = [
        "adk",
        "run",
        "victim_agent",
    ]

    process = subprocess.run(
        command,
        cwd=ROOT,
        input=(
            mission
            + "\n"
            + "exit\n"
        ),
        text=True,
        capture_output=True,
    )

    transcript = (
        process.stdout
        + "\n"
        + process.stderr
    )

    transcript_path = (
        scenario_dir
        / "orchestrated-terminal.txt"
    )

    transcript_path.write_text(
        transcript
    )

    print()
    print(transcript)

    if process.returncode != 0:
        raise SystemExit(
            "STOP: frozen refund victim replay failed."
        )

    # First prove the consequential external action.
    run_module(
        "toolsuture.verify_action_recovery",
        "--scenario",
        scenario,
    )

    # Only then prove the complete frozen-agent mission.
    run_module(
        "toolsuture.verify_mission",
        "--scenario",
        scenario,
        "--terminal",
        str(
            transcript_path.relative_to(
                ROOT
            )
        ),
    )

    verification = load_json(
        canonical_proof
    )

    shutil.copy2(
        canonical_proof,
        scenario_dir
        / "orchestrated-verification.json",
    )

    if not verification.get(
        "mission_completed"
    ):
        raise SystemExit(
            "STOP: refund mission was not "
            "independently verified."
        )

    return {
        "replay_id":
            verification.get(
                "replay_id",
                replay.get(
                    "replay_id"
                ),
            ),

        "mission_completed":
            True,

        "after":
            verification.get(
                "after"
            ),

        "victim_source_changed":
            verification.get(
                "victim_source_changed"
            ),
    }


@dataclass(frozen=True)
class RecoveryHandler:
    name: str
    old_tool: str
    new_tool: str

    # None = response shape does not matter.
    # True = response repair operations required.
    # False = no response repair operations allowed.
    requires_response_operations: bool | None

    runner: Callable[
        [Path],
        dict,
    ]

    def matches(
        self,
        plan: dict,
    ) -> bool:
        if (
            plan.get("old_tool")
            != self.old_tool
        ):
            return False

        if (
            plan.get("new_tool")
            != self.new_tool
        ):
            return False

        if (
            self.requires_response_operations
            is None
        ):
            return True

        has_response_operations = bool(
            plan.get(
                "response_operations",
                [],
            )
        )

        return (
            has_response_operations
            == self.requires_response_operations
        )


RECOVERY_HANDLERS = (
    RecoveryHandler(
        name="request-migration-refund",
        old_tool="refund_order",
        new_tool="issue_refund",
        requires_response_operations=False,
        runner=run_refund_replay,
    ),

    RecoveryHandler(
        name="bidirectional-shipment",
        old_tool="lookup_shipment",
        new_tool="lookup_shipment",
        requires_response_operations=True,
        runner=run_shipment_replay,
    ),
)


def resolve_recovery_handler(
    plan: dict,
) -> RecoveryHandler | None:
    matches = [
        handler
        for handler in RECOVERY_HANDLERS
        if handler.matches(plan)
    ]

    if not matches:
        return None

    if len(matches) > 1:
        names = ", ".join(
            handler.name
            for handler in matches
        )

        raise SystemExit(
            "STOP: ambiguous recovery route: "
            + names
        )

    return matches[0]

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run ToolSuture as a dynamic "
            "repair-or-hold state machine."
        )
    )

    parser.add_argument(
        "--scenario",
        required=True,
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Use existing diagnosis/policy/"
            "plan artifacts instead of "
            "regenerating them."
        ),
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Deploy and replay when policy "
            "and validation allow execution."
        ),
    )

    args = parser.parse_args()

    scenario_dir = (
        SCENARIOS
        / args.scenario
    )

    if not scenario_dir.exists():
        raise SystemExit(
            f"STOP: unknown scenario {args.scenario}"
        )

    started_at = datetime.now(
        timezone.utc
    ).isoformat()

    run_id = str(
        uuid.uuid4()
    )

    # Immediately replace any stale canonical success.
    # From this point forward the newest attempt is explicit.
    write_orchestration(
        scenario_dir,
        {
            "scenario":
                args.scenario,

            "run_id":
                run_id,

            "started_at":
                started_at,

            "finished_at":
                None,

            "mode":
                "IN_PROGRESS",

            "execution_attempted":
                False,

            "mission_completed":
                False,

            "reason":
                "Recovery attempt is in progress.",
        },
    )

    print()
    print("========================================")
    print("TOOLSUTURE RECOVERY ORCHESTRATOR")
    print("========================================")
    print(
        "scenario:",
        args.scenario,
    )
    print(
        "resume:",
        args.resume,
    )
    print(
        "execute:",
        args.execute,
    )

    # ----------------------------------
    # OBSERVE
    # ----------------------------------

    print()
    print("OBSERVE")

    require_scenario_inputs(
        scenario_dir
    )

    print(
        "  ✓ mission"
    )
    print(
        "  ✓ old contract"
    )
    print(
        "  ✓ new contract"
    )
    print(
        "  ✓ provider semantics"
    )

    # ----------------------------------
    # DIAGNOSE
    # ----------------------------------

    print()
    print("DIAGNOSE")

    diagnosis_path = (
        scenario_dir
        / "diagnosis.json"
    )

    if not args.resume:
        run_module(
            "toolsuture.diagnose_case",
            "--scenario",
            args.scenario,
        )

    diagnosis = load_json(
        diagnosis_path
    )

    print(
        "  decision:",
        diagnosis.get(
            "decision"
        ),
    )

    print(
        "  risk:",
        diagnosis.get(
            "risk_level"
        ),
    )

    # ----------------------------------
    # POLICY
    # ----------------------------------

    print()
    print("POLICY")

    policy_path = (
        scenario_dir
        / "policy.json"
    )

    if not args.resume:
        run_module(
            "toolsuture.policy_case",
            "--scenario",
            args.scenario,
        )

    policy = load_json(
        policy_path
    )

    print(
        "  gate:",
        policy.get("gate"),
    )

    print(
        "  auto repair:",
        policy.get(
            "auto_repair_allowed"
        ),
    )

    # ----------------------------------
    # DYNAMIC TRANSITION
    # ----------------------------------

    approved = (
        policy.get("gate")
        == "APPROVED"
        and policy.get(
            "auto_repair_allowed"
        )
        is True
    )

    if not approved:
        result = {
            "scenario":
                args.scenario,

            "started_at":
                started_at,

            "finished_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "mode":
                "SAFE_HOLD",

            "execution_attempted":
                False,

            "diagnosis_decision":
                diagnosis.get(
                    "decision"
                ),

            "risk_level":
                diagnosis.get(
                    "risk_level"
                ),

            "policy_gate":
                policy.get(
                    "gate"
                ),

            "mission_completed":
                False,

            "reason":
                "Policy did not authorize automatic execution.",
        }

        print()
        print("========================================")
        print("MODE: SAFE HOLD")
        print("NO EXECUTION")
        print("========================================")

        write_orchestration(
            scenario_dir,
            result,
        )

        return

    print()
    print("========================================")
    print("MODE: RECOVERY")
    print("POLICY AUTHORIZED FORWARD PLAY")
    print("========================================")

    # ----------------------------------
    # PLAN
    # ----------------------------------

    print()
    print("PLAN")

    plan_path = (
        scenario_dir
        / "repair-plan.json"
    )

    if not args.resume:
        run_module(
            "toolsuture.plan_case",
            "--scenario",
            args.scenario,
        )

    plan = load_json(
        plan_path
    )

    print(
        "  scope:",
        plan.get("scope"),
    )

    print(
        "  decision:",
        plan.get(
            "decision"
        ),
    )

    # ----------------------------------
    # VALIDATE
    # ----------------------------------

    print()
    print("VALIDATE")

    validation_path = (
        scenario_dir
        / "plan-validation.json"
    )

    if not args.resume:
        run_module(
            "toolsuture.validate_plan",
            "--scenario",
            args.scenario,
        )

    validation = load_json(
        validation_path
    )

    validated = (
        validation.get("gate")
        == "VALIDATED"
        and validation.get(
            "execution_allowed"
        )
        is True
        and not validation.get(
            "reasons"
        )
    )

    print(
        "  gate:",
        validation.get(
            "gate"
        ),
    )

    print(
        "  execution allowed:",
        validation.get(
            "execution_allowed"
        ),
    )

    if not validated:
        result = {
            "scenario":
                args.scenario,

            "started_at":
                started_at,

            "finished_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "mode":
                "SAFE_HOLD",

            "execution_attempted":
                False,

            "diagnosis_decision":
                diagnosis.get(
                    "decision"
                ),

            "policy_gate":
                policy.get(
                    "gate"
                ),

            "validation_gate":
                validation.get(
                    "gate"
                ),

            "mission_completed":
                False,

            "reason":
                "Deterministic validation did not authorize deployment.",
        }

        print()
        print("========================================")
        print("TRANSITION ABORTED")
        print("BACK TO SAFE HOLD")
        print("========================================")

        write_orchestration(
            scenario_dir,
            result,
        )

        return

    if not args.execute:
        result = {
            "scenario":
                args.scenario,

            "started_at":
                started_at,

            "finished_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "mode":
                "RECOVERY_READY",

            "execution_attempted":
                False,

            "diagnosis_decision":
                diagnosis.get(
                    "decision"
                ),

            "policy_gate":
                policy.get(
                    "gate"
                ),

            "validation_gate":
                validation.get(
                    "gate"
                ),

            "mission_completed":
                False,

            "reason":
                "Execution not requested.",
        }

        print()
        print("========================================")
        print("RECOVERY READY")
        print("DEPLOYMENT NOT REQUESTED")
        print("========================================")

        write_orchestration(
            scenario_dir,
            result,
        )

        return

    # ----------------------------------
    # RESOLVE EXECUTION ROUTE
    # ----------------------------------

    print()
    print("EXECUTION ROUTE")

    handler = resolve_recovery_handler(
        plan
    )

    if handler is None:
        result = {
            "scenario":
                args.scenario,

            "started_at":
                started_at,

            "finished_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "mode":
                "SAFE_HOLD",

            "execution_attempted":
                False,

            "diagnosis_decision":
                diagnosis.get(
                    "decision"
                ),

            "risk_level":
                diagnosis.get(
                    "risk_level"
                ),

            "policy_gate":
                policy.get(
                    "gate"
                ),

            "validation_gate":
                validation.get(
                    "gate"
                ),

            "mission_completed":
                False,

            "reason":
                (
                    "No registered deterministic "
                    "recovery handler matches this "
                    "validated repair shape."
                ),
        }

        print(
            "  handler: NONE"
        )
        print()
        print("========================================")
        print("MODE: SAFE HOLD")
        print("UNKNOWN EXECUTION SHAPE")
        print("NO DEPLOYMENT")
        print("========================================")

        write_orchestration(
            scenario_dir,
            result,
        )

        return

    print(
        "  handler:",
        handler.name,
    )

    print(
        "  old tool:",
        handler.old_tool,
    )

    print(
        "  new tool:",
        handler.new_tool,
    )

    # ----------------------------------
    # DEPLOY + REPLAY TRANSACTION
    # ----------------------------------

    deployment_snapshot = (
        snapshot_deployment()
    )

    try:
        print()
        print("DEPLOY")

        run_module(
            "toolsuture.deploy_adapter",
            "--scenario",
            args.scenario,
        )

        # ----------------------------------
        # REPLAY + VERIFY
        # ----------------------------------

        recovery = handler.runner(
            scenario_dir
        )

    except SystemExit as exc:
        failure = inspect_failed_replay(
            scenario_dir
        )

        tool_call_observed = (
            failure[
                "tool_call_observed"
            ]
        )

        # Unai does not infer the rebound from the transcript.
        # Independently inspect replay-linked provider/audit state.
        try:
            effect = probe_scenario(
                args.scenario
            )

        except Exception as probe_exc:
            effect = {
                "effect_class":
                    "EFFECT_PROBE_FAILED",

                "effect_verified":
                    False,

                "probe_error":
                    str(probe_exc),
            }

        effect_class = effect.get(
            "effect_class",
            "EFFECT_UNCERTAIN",
        )

        # ----------------------------------------------------
        # Nothing happened externally.
        # Safe to restore previous deployment.
        # ----------------------------------------------------

        if (
            effect_class
            == "NO_EFFECT_OBSERVED"
        ):
            restore_deployment(
                deployment_snapshot
            )

            failure_mode = (
                "RECOVERY_INTERRUPTED"
            )

            adapter_state = (
                "PREVIOUS_DEPLOYMENT_RESTORED"
            )

            rollback_safe = True

        # ----------------------------------------------------
        # Read-only operation really executed.
        # No consequential mutation must be undone, but the
        # complete agent mission still failed.
        # ----------------------------------------------------

        elif (
            effect_class
            == "VERIFIED_READ_ONLY_EXECUTION"
        ):
            restore_deployment(
                deployment_snapshot
            )

            failure_mode = (
                "RECOVERY_INTERRUPTED_READ_ONLY"
            )

            adapter_state = (
                "PREVIOUS_DEPLOYMENT_RESTORED"
            )

            rollback_safe = True

        # ----------------------------------------------------
        # Consequential action really occurred.
        # NEVER retry automatically.
        # Adapter is disabled and operator escalation required.
        # ----------------------------------------------------

        elif (
            effect_class
            == "VERIFIED_CONSEQUENTIAL_ACTION"
        ):
            disable_current_adapter(
                "Consequential action verified "
                "but complete mission failed."
            )

            failure_mode = (
                "PARTIAL_ACTION"
            )

            adapter_state = (
                "DISABLED_PENDING_VERIFICATION"
            )

            rollback_safe = False

        # ----------------------------------------------------
        # Evidence is uncertain or unsupported.
        # Fail closed.
        # ----------------------------------------------------

        else:
            disable_current_adapter(
                "Replay failed and external effect "
                "could not be safely determined."
            )

            failure_mode = (
                "VERIFICATION_REQUIRED"
            )

            adapter_state = (
                "DISABLED_PENDING_VERIFICATION"
            )

            rollback_safe = False

        result = {
            "scenario":
                args.scenario,

            "run_id":
                run_id,

            "started_at":
                started_at,

            "finished_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "mode":
                failure_mode,

            "execution_attempted":
                True,

            "diagnosis_decision":
                diagnosis.get(
                    "decision"
                ),

            "risk_level":
                diagnosis.get(
                    "risk_level"
                ),

            "policy_gate":
                policy.get(
                    "gate"
                ),

            "validation_gate":
                validation.get(
                    "gate"
                ),

            "handler":
                handler.name,

            "mission_completed":
                False,

            "error_class":
                failure[
                    "error_class"
                ],

            "tool_list_observed":
                failure[
                    "tool_list_observed"
                ],

            "tool_call_observed":
                tool_call_observed,

            "effect_probe":
                effect.get(
                    "probe"
                ),

            "effect_class":
                effect_class,

            "effect_verified":
                effect.get(
                    "effect_verified",
                    False,
                ),

            "quota_failure_observed":
                failure[
                    "quota_failure_observed"
                ],

            "adapter_state":
                adapter_state,

            "automatic_rollback_safe":
                rollback_safe,

            "reason":
                str(exc),
        }

        write_orchestration(
            scenario_dir,
            result,
        )

        print()
        print("========================================")
        print(
            "RECOVERY DID NOT COMPLETE"
        )
        print(
            "mode:",
            failure_mode,
        )
        print(
            "error:",
            failure[
                "error_class"
            ],
        )
        print(
            "tool call observed:",
            tool_call_observed,
        )
        print(
            "adapter:",
            adapter_state,
        )
        print("========================================")

        return

    result = {
        "scenario":
            args.scenario,

        "started_at":
            started_at,

        "finished_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "mode":
            "RECOVERY_COMPLETE",

        "execution_attempted":
            True,

        "diagnosis_decision":
            diagnosis.get(
                "decision"
            ),

        "risk_level":
            diagnosis.get(
                "risk_level"
            ),

        "policy_gate":
            policy.get(
                "gate"
            ),

        "validation_gate":
            validation.get(
                "gate"
            ),

        "handler":
            handler.name,

        "replay_id":
            recovery.get(
                "replay_id"
            ),

        "mission_completed":
            recovery.get(
                "mission_completed"
            ),

        "after":
            recovery.get(
                "after"
            ),

        "victim_source_changed":
            recovery.get(
                "victim_source_changed"
            ),
    }

    write_orchestration(
        scenario_dir,
        result,
    )

    print()
    print("========================================")
    print("MISSION COMPLETED AND VERIFIED")
    print("DYNAMIC RECOVERY COMPLETE")
    print("========================================")


if __name__ == "__main__":
    main()
