import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BANK = (
    ROOT
    / "evidence"
    / "banked"
    / "score-3-0"
)


def load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"STOP: required proof missing: {path}"
        )

    return json.loads(
        path.read_text()
    )


def copy_file(
    source: Path,
    destination: Path,
) -> None:
    if not source.exists():
        raise SystemExit(
            f"STOP: evidence missing: {source}"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        source,
        destination,
    )


def digest(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(65536),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def require_true_checks(
    data: dict,
    label: str,
) -> None:
    checks = data.get(
        "checks",
        {}
    )

    if not checks:
        raise SystemExit(
            f"STOP: {label} contains no checks."
        )

    failed = [
        key
        for key, value in checks.items()
        if value is not True
    ]

    if failed:
        raise SystemExit(
            f"STOP: {label} failed checks: "
            + ", ".join(failed)
        )


# ============================================================
# CLEAN REBUILD
# ============================================================

if BANK.exists():
    shutil.rmtree(
        BANK
    )

BANK.mkdir(
    parents=True,
    exist_ok=True,
)

goal1 = (
    BANK
    / "goal-1-safe-return"
)

goal2 = (
    BANK
    / "goal-2-response-reshape"
)

goal3 = (
    BANK
    / "goal-3-blind-generalization"
)


# ============================================================
# GOAL 1
#
# Legacy proof schema:
# - action artifact owns replay provenance
# - mission artifact owns mission completion
# - terminal owns frozen-agent behavior
# ============================================================

safe = (
    ROOT
    / "evidence"
    / "scenarios"
    / "safe-return"
)

action = load(
    safe
    / "action-recovery-verification.json"
)

mission_path = (
    safe
    / "pre-registry-verified-proof.json"
)

if not mission_path.exists():
    mission_path = (
        safe
        / "mission-verification.json"
    )

mission = load(
    mission_path
)

terminal_path = (
    safe
    / "victim-replay-terminal.txt"
)

if not terminal_path.exists():
    raise SystemExit(
        "STOP: Goal 1 successful terminal proof missing."
    )

terminal = terminal_path.read_text(
    errors="replace"
)


if (
    action.get("proof_level")
    != "REPLAY_LINKED_ACTION_VERIFIED"
):
    raise SystemExit(
        "STOP: Goal 1 action is not replay-linked verified."
    )

if (
    action.get("action_restored")
    is not True
):
    raise SystemExit(
        "STOP: Goal 1 action was not restored."
    )

require_true_checks(
    action,
    "Goal 1 action proof",
)

record = action.get(
    "provider_record",
    {}
)

if (
    record.get("provider_version")
    != "v2"
):
    raise SystemExit(
        "STOP: Goal 1 provider is not v2."
    )

if (
    record.get("status")
    != "refunded"
):
    raise SystemExit(
        "STOP: Goal 1 refund was not verified."
    )

if (
    mission.get("mission_completed")
    is not True
):
    raise SystemExit(
        "STOP: Goal 1 mission is not completed."
    )

if (
    mission.get("after")
    != "CAPABILITY_RESTORED"
):
    raise SystemExit(
        "STOP: Goal 1 capability was not restored."
    )

require_true_checks(
    mission,
    "Goal 1 mission proof",
)

# The legacy mission proof may not carry replay_id.
# Do NOT invent one. The action proof is the provenance root.
mission_replay = mission.get(
    "replay_id"
)

action_replay = action.get(
    "replay_id"
)

if not action_replay:
    raise SystemExit(
        "STOP: Goal 1 action replay ID missing."
    )

if (
    mission_replay is not None
    and mission_replay != action_replay
):
    raise SystemExit(
        "STOP: Goal 1 proof replay IDs conflict."
    )


terminal_requirements = (
    "ListToolsRequest",
    "CallToolRequest",
    "[refund_agent]:",
    "successfully processed",
    "ORD-1002",
    "$24.99",
)

missing_terminal = [
    item
    for item in terminal_requirements
    if item not in terminal
]

if missing_terminal:
    raise SystemExit(
        "STOP: Goal 1 successful transcript "
        "missing: "
        + ", ".join(
            missing_terminal
        )
    )

if (
    "RESOURCE_EXHAUSTED"
    in terminal
):
    raise SystemExit(
        "STOP: Goal 1 bank transcript contains quota failure."
    )

if (
    "Traceback (most recent call last)"
    in terminal
):
    raise SystemExit(
        "STOP: Goal 1 bank transcript contains traceback."
    )


for name in (
    "action-recovery-verification.json",
    "repair-plan.json",
    "plan-validation.json",
    "policy.json",
    "diagnosis.json",
    "mission.txt",
    "victim-replay-terminal.txt",
):
    copy_file(
        safe / name,
        goal1 / name,
    )

copy_file(
    mission_path,
    goal1
    / "mission-verification.json",
)


goal1_summary = {
    "goal": 1,

    "status":
        "VERIFIED",

    "replay_id":
        action_replay,

    "proof_model":
        (
            "Replay provenance from action proof; "
            "mission completion from legacy mission proof; "
            "frozen-agent behavior from successful transcript."
        ),

    "mission_proof_contains_replay_id":
        mission_replay is not None,

    "provider_version":
        record.get(
            "provider_version"
        ),

    "provider_status":
        record.get(
            "status"
        ),

    "victim_source_unchanged":
        action.get(
            "checks",
            {},
        ).get(
            "victim_source_unchanged"
        ),
}

(
    goal1
    / "goal-summary.json"
).write_text(
    json.dumps(
        goal1_summary,
        indent=2,
    )
)

print(
    "GOAL 1: VERIFIED"
)
print(
    "  replay:",
    action_replay,
)
print(
    "  legacy mission replay field:",
    (
        mission_replay
        if mission_replay
        else "ABSENT — action proof supplies provenance"
    ),
)


# ============================================================
# GOAL 2
#
# orchestrated-verification.json is self-contained:
# replay ID + checks + audit event + completion.
# ============================================================

shipment = (
    ROOT
    / "evidence"
    / "scenarios"
    / "response-reshape"
)

ship = load(
    shipment
    / "orchestrated-verification.json"
)

if (
    ship.get("mission_completed")
    is not True
):
    raise SystemExit(
        "STOP: Goal 2 mission is not completed."
    )

if (
    ship.get("after")
    != "CAPABILITY_RESTORED"
):
    raise SystemExit(
        "STOP: Goal 2 capability was not restored."
    )

if (
    ship.get(
        "victim_source_changed"
    )
    is not False
):
    raise SystemExit(
        "STOP: Goal 2 victim integrity failed."
    )

if not ship.get(
    "replay_id"
):
    raise SystemExit(
        "STOP: Goal 2 replay ID missing."
    )

require_true_checks(
    ship,
    "Goal 2 verification",
)

event = ship.get(
    "audit_event",
    {}
)

if (
    event.get("replay_id")
    != ship.get("replay_id")
):
    raise SystemExit(
        "STOP: Goal 2 audit provenance mismatch."
    )

if (
    event.get("raw_v2_response")
    is None
):
    raise SystemExit(
        "STOP: Goal 2 native v2 response missing."
    )

if (
    event.get(
        "reconstructed_v1_response"
    )
    is None
):
    raise SystemExit(
        "STOP: Goal 2 reconstructed v1 response missing."
    )


for name in (
    "orchestrated-verification.json",
    "repair-plan.json",
    "plan-validation.json",
    "policy.json",
    "diagnosis.json",
    "break-verification.json",
    "mission.txt",
):
    copy_file(
        shipment / name,
        goal2 / name,
    )


goal2_summary = {
    "goal": 2,

    "status":
        "VERIFIED",

    "replay_id":
        ship["replay_id"],

    "failure_class":
        ship.get(
            "failure_class"
        ),

    "before":
        ship.get(
            "before"
        ),

    "after":
        ship.get(
            "after"
        ),

    "victim_source_changed":
        ship.get(
            "victim_source_changed"
        ),

    "native_v2_response_observed":
        ship.get(
            "checks",
            {},
        ).get(
            "native_v2_response_observed"
        ),

    "v1_response_reconstructed":
        ship.get(
            "checks",
            {},
        ).get(
            "v1_response_reconstructed"
        ),
}

(
    goal2
    / "goal-summary.json"
).write_text(
    json.dumps(
        goal2_summary,
        indent=2,
    )
)

print(
    "GOAL 2: VERIFIED"
)
print(
    "  replay:",
    ship["replay_id"],
)


# ============================================================
# GOAL 3 — BLIND 5/5
# ============================================================

blind = (
    ROOT
    / "evidence"
    / "evaluation"
    / "blind-v1"
)

engine_hash = (
    blind
    / "engine.sha256"
)

fixture_hash = (
    blind
    / "fixtures.sha256"
)

if not engine_hash.exists():
    raise SystemExit(
        "STOP: blind engine hash file missing."
    )

if not fixture_hash.exists():
    raise SystemExit(
        "STOP: blind fixture hash file missing."
    )


score_candidates = []

for candidate in blind.glob(
    "*.json"
):
    try:
        data = json.loads(
            candidate.read_text()
        )
    except Exception:
        continue

    if (
        data.get("evaluation")
        == "blind-v1"
        and data.get(
            "cases_total"
        )
        == 5
        and data.get(
            "cases_completed"
        )
        == 5
        and data.get(
            "cases_passed"
        )
        == 5
        and data.get(
            "case_accuracy"
        )
        == 1.0
        and data.get(
            "check_accuracy"
        )
        == 1.0
    ):
        score_candidates.append(
            (
                candidate,
                data,
            )
        )


if not score_candidates:
    raise SystemExit(
        "STOP: verified blind 5/5 result not found."
    )

score_path, score = (
    score_candidates[-1]
)


results = score.get(
    "results",
    []
)

if (
    len(results)
    != 5
):
    raise SystemExit(
        "STOP: blind result count is not 5."
    )

if not all(
    result.get("passed")
    is True
    for result in results
):
    raise SystemExit(
        "STOP: one or more blind cases failed."
    )


copy_file(
    score_path,
    goal3
    / "blind-score.json",
)

copy_file(
    engine_hash,
    goal3
    / "engine.sha256",
)

copy_file(
    fixture_hash,
    goal3
    / "fixtures.sha256",
)


goal3_summary = {
    "goal": 3,

    "status":
        "VERIFIED",

    "cases_total":
        5,

    "cases_completed":
        5,

    "cases_passed":
        5,

    "case_accuracy":
        1.0,

    "check_accuracy":
        1.0,
}

(
    goal3
    / "goal-summary.json"
).write_text(
    json.dumps(
        goal3_summary,
        indent=2,
    )
)

print(
    "GOAL 3: VERIFIED"
)
print(
    "  blind score: 5/5"
)


# ============================================================
# SCOREBOARD
# ============================================================

copy_file(
    ROOT
    / "victim_agent.sha256",
    BANK
    / "victim_agent.sha256",
)

copy_file(
    ROOT
    / "shipment_victim.sha256",
    BANK
    / "shipment_victim.sha256",
)


scoreboard = {
    "score":
        "3-0",

    "status":
        "BANKED_VERIFIED",

    "goals": [
        goal1_summary,
        goal2_summary,
        goal3_summary,
    ],

    "goal_4": {
        "status":
            "NOT_YET_SCORED",

        "required_live_test": [
            "dangerous incident -> SAFE_HOLD",
            "safe-return -> RECOVERY_COMPLETE",
            "response-reshape -> RECOVERY_COMPLETE",
        ],

        "constraint":
            "No code edits between the three live tests.",
    },
}

(
    BANK
    / "scoreboard.json"
).write_text(
    json.dumps(
        scoreboard,
        indent=2,
    )
)


# ============================================================
# MANIFEST
# ============================================================

files = [
    path
    for path in BANK.rglob("*")
    if (
        path.is_file()
        and path.name
        not in {
            "manifest.json",
            "manifest.sha256",
        }
    )
]

manifest = {
    str(
        path.relative_to(
            BANK
        )
    ):
        digest(path)

    for path in sorted(
        files
    )
}

(
    BANK
    / "manifest.json"
).write_text(
    json.dumps(
        manifest,
        indent=2,
    )
)

with (
    BANK
    / "manifest.sha256"
).open("w") as f:
    for relative, sha in sorted(
        manifest.items()
    ):
        f.write(
            f"{sha}  {relative}\n"
        )


print()
print(
    "========================================"
)
print(
    "SPAIN 3-0: VERIFIED PROOF BANK COMPLETE"
)
print(
    "========================================"
)


if __name__ == "__main__":
    pass
