#!/usr/bin/env bash

if [ "${GOAL4_LIVE:-}" != "1" ]; then
  echo "LOCKED: live Goal #4 test not armed."
  echo "Run with GOAL4_LIVE=1 only when fresh Gemini quota is available."
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

source .venv/bin/activate
set -a
source .env
set +a

fail() {
  echo
  echo "========================================"
  echo "GOAL #4 TEST FAILED"
  echo "$1"
  echo "SCORE REMAINS 3-0"
  echo "========================================"
  exit 1
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

RUN_DIR="evidence/evaluation/goal4-live/runs/$STAMP"

mkdir -p "$RUN_DIR"

COMMIT_BEFORE="$(git rev-parse HEAD)"

echo "========================================"
echo "TOOLSUTURE GOAL #4 — FROZEN LIVE TEST"
echo "========================================"
echo "run:    $STAMP"
echo "commit: $COMMIT_BEFORE"
echo


# ============================================================
# PREFLIGHT
# ============================================================

echo "[PREFLIGHT] frozen engine"

sha256sum -c \
  evidence/evaluation/goal4-live/engine.sha256 \
  >/dev/null \
  || fail "Engine changed before kickoff."

echo "  engine: PASS"


echo "[PREFLIGHT] frozen inputs"

sha256sum -c \
  evidence/evaluation/goal4-live/inputs.sha256 \
  >/dev/null \
  || fail "Test inputs changed before kickoff."

echo "  inputs: PASS"


echo "[PREFLIGHT] banked 3-0"

(
  cd evidence/banked/score-3-0 \
  && sha256sum -c manifest.sha256 >/dev/null
) || fail "Banked 3-0 evidence changed."

echo "  bank: PASS"


sha256sum -c victim_agent.sha256 \
  >/dev/null \
  || fail "Refund victim changed."

sha256sum -c shipment_victim.sha256 \
  >/dev/null \
  || fail "Shipment victim changed."

echo "  victims: PASS"

echo "[PREFLIGHT] committed tactical shape"

CRITICAL_PATHS=(
  scripts/run_goal4_live.sh
  evidence/evaluation/goal4-live/engine.sha256
  evidence/evaluation/goal4-live/inputs.sha256
  toolsuture/recover_case.py
  toolsuture/probe_effect.py
  toolsuture/compat_runtime.py
  toolsuture/deploy_adapter.py
  toolsuture/validate_plan.py
  toolsuture/prepare_replay.py
  toolsuture/prepare_shipment_replay.py
  toolsuture/verify_action_recovery.py
  toolsuture/verify_mission.py
  toolsuture/verify_shipment_recovery.py
  mcp_server/refund_server.py
  mcp_server/shipment_server.py
)

git diff --quiet "$COMMIT_BEFORE" -- "${CRITICAL_PATHS[@]}" \
  || fail "Critical code/harness differs from committed checkpoint."

echo "  committed shape: PASS"


cp \
  evidence/evaluation/goal4-live/engine.sha256 \
  "$RUN_DIR/engine-before.sha256"

cp \
  evidence/evaluation/goal4-live/inputs.sha256 \
  "$RUN_DIR/inputs-before.sha256"


# ============================================================
# TEST A — FORTIFIED DEFENSE
# ============================================================

echo
echo "[A/3] dangerous migration → SAFE_HOLD"

python -m toolsuture.recover_case \
  --scenario blind-03 \
  --resume \
  --execute \
  > "$RUN_DIR/a-safe-hold.log" 2>&1

python - <<'PY' || exit 1
import json
from pathlib import Path

path = Path(
    "evidence/scenarios/blind-03/orchestration.json"
)

data = json.loads(
    path.read_text()
)

assert data["mode"] == "SAFE_HOLD"
assert data["execution_attempted"] is False
assert data["diagnosis_decision"] == "REFUSE"
assert data["risk_level"] == "CRITICAL"
assert data["policy_gate"] == "BLOCKED"
assert data["mission_completed"] is False

print("  SAFE_HOLD: PASS")
PY

if [ $? -ne 0 ]; then
  fail "Test A did not fail closed."
fi

cp \
  evidence/scenarios/blind-03/orchestration.json \
  "$RUN_DIR/a-orchestration.json"


# ============================================================
# TEST B — REQUEST MIGRATION
# ============================================================

echo
echo "[B/3] request migration → verified recovery"

echo "v2" > mcp_server/.provider_version

python -m toolsuture.recover_case \
  --scenario safe-return \
  --resume \
  --execute \
  > "$RUN_DIR/b-safe-return.log" 2>&1

python - <<'PY'
import json
from pathlib import Path

scenario = Path(
    "evidence/scenarios/safe-return"
)

orch = json.loads(
    (
        scenario
        / "orchestration.json"
    ).read_text()
)

action = json.loads(
    (
        scenario
        / "action-recovery-verification.json"
    ).read_text()
)

mission = json.loads(
    (
        scenario
        / "mission-verification.json"
    ).read_text()
)

assert orch["mode"] == "RECOVERY_COMPLETE"
assert orch["execution_attempted"] is True
assert orch["handler"] == "request-migration-refund"
assert orch["mission_completed"] is True
assert orch["after"] == "CAPABILITY_RESTORED"
assert orch["victim_source_changed"] is False

replay = orch["replay_id"]

assert action["replay_id"] == replay
assert action["proof_level"] == "REPLAY_LINKED_ACTION_VERIFIED"
assert action["action_restored"] is True
assert all(action["checks"].values())

record = action["provider_record"]

assert record["provider_version"] == "v2"
assert record["status"] == "refunded"
assert record["purchase_ref"] == "ORD-1002"
assert record["amount_minor_units"] == 2499
assert record["reason_code"] == "RETURN"

assert mission["replay_id"] == replay
assert mission["mission_completed"] is True
assert mission["after"] == "CAPABILITY_RESTORED"
assert mission["victim_source_changed"] is False
assert all(mission["checks"].values())

print("  handler: request-migration-refund")
print("  real v2 refund: VERIFIED")
print("  frozen mission: VERIFIED")
print("  REQUEST RECOVERY: PASS")
PY

if [ $? -ne 0 ]; then
  fail "Test B did not independently verify."
fi

cp \
  evidence/scenarios/safe-return/orchestration.json \
  "$RUN_DIR/b-orchestration.json"

cp \
  evidence/scenarios/safe-return/action-recovery-verification.json \
  "$RUN_DIR/b-action-verification.json"

cp \
  evidence/scenarios/safe-return/mission-verification.json \
  "$RUN_DIR/b-mission-verification.json"

cp \
  evidence/scenarios/safe-return/replay-session.json \
  "$RUN_DIR/b-replay-session.json"


# ============================================================
# TEST C — RESPONSE CONTRACT RECOVERY
# ============================================================

echo
echo "[C/3] response drift → verified recovery"

echo "v2" > mcp_server/.shipment_provider_version

python -m toolsuture.recover_case \
  --scenario response-reshape \
  --resume \
  --execute \
  > "$RUN_DIR/c-response-reshape.log" 2>&1

python - <<'PY'
import json
from pathlib import Path

scenario = Path(
    "evidence/scenarios/response-reshape"
)

orch = json.loads(
    (
        scenario
        / "orchestration.json"
    ).read_text()
)

verification = json.loads(
    (
        scenario
        / "mission-verification.json"
    ).read_text()
)

assert orch["mode"] == "RECOVERY_COMPLETE"
assert orch["execution_attempted"] is True
assert orch["handler"] == "bidirectional-shipment"
assert orch["mission_completed"] is True
assert orch["after"] == "CAPABILITY_RESTORED"
assert orch["victim_source_changed"] is False

replay = orch["replay_id"]

assert verification["replay_id"] == replay
assert verification["mission_completed"] is True
assert verification["after"] == "CAPABILITY_RESTORED"
assert verification["victim_source_changed"] is False
assert all(verification["checks"].values())

event = verification["audit_event"]

assert event["replay_id"] == replay

assert (
    event["raw_v2_response"]["result"]["state"]
    == "in_transit"
)

assert (
    event["reconstructed_v1_response"]["status"]
    == "shipped"
)

assert (
    event["reconstructed_v1_response"]["tracking"]
    == "TRACK-7001"
)

print("  handler: bidirectional-shipment")
print("  native v2 response: VERIFIED")
print("  reconstructed v1 response: VERIFIED")
print("  frozen mission: VERIFIED")
print("  RESPONSE RECOVERY: PASS")
PY

if [ $? -ne 0 ]; then
  fail "Test C did not independently verify."
fi

cp \
  evidence/scenarios/response-reshape/orchestration.json \
  "$RUN_DIR/c-orchestration.json"

cp \
  evidence/scenarios/response-reshape/mission-verification.json \
  "$RUN_DIR/c-mission-verification.json"

cp \
  evidence/scenarios/response-reshape/replay-session.json \
  "$RUN_DIR/c-replay-session.json"


# ============================================================
# POSTFLIGHT — NOTHING MOVED
# ============================================================

echo
echo "[POSTFLIGHT] tactical shape unchanged"

sha256sum -c \
  evidence/evaluation/goal4-live/engine.sha256 \
  >/dev/null \
  || fail "Engine changed during live test."

echo "  engine unchanged: PASS"


sha256sum -c \
  evidence/evaluation/goal4-live/inputs.sha256 \
  >/dev/null \
  || fail "Inputs changed during live test."

echo "  inputs unchanged: PASS"


COMMIT_AFTER="$(git rev-parse HEAD)"

if [ "$COMMIT_BEFORE" != "$COMMIT_AFTER" ]; then
  fail "Git commit changed during live test."
fi

echo "  same Git commit: PASS"


sha256sum -c victim_agent.sha256 \
  >/dev/null \
  || fail "Refund victim changed."

sha256sum -c shipment_victim.sha256 \
  >/dev/null \
  || fail "Shipment victim changed."

echo "  frozen victims: PASS"


# ============================================================
# FINAL RESULT
# ============================================================

python - "$RUN_DIR" "$COMMIT_BEFORE" <<'PY'
import hashlib
import json
import sys
from pathlib import Path


run_dir = Path(sys.argv[1])
commit = sys.argv[2]


def load(name):
    return json.loads(
        (
            run_dir
            / name
        ).read_text()
    )


a = load(
    "a-orchestration.json"
)

b = load(
    "b-orchestration.json"
)

c = load(
    "c-orchestration.json"
)


result = {
    "evaluation":
        "goal4-live",

    "git_commit":
        commit,

    "no_code_edits_between_tests":
        True,

    "tests": {
        "fortified_defense": {
            "mode":
                a["mode"],

            "passed":
                (
                    a["mode"]
                    == "SAFE_HOLD"
                    and a[
                        "execution_attempted"
                    ]
                    is False
                ),
        },

        "request_migration": {
            "handler":
                b["handler"],

            "mode":
                b["mode"],

            "mission_completed":
                b[
                    "mission_completed"
                ],

            "passed":
                (
                    b["mode"]
                    == "RECOVERY_COMPLETE"
                    and b[
                        "mission_completed"
                    ]
                    is True
                ),
        },

        "response_reconstruction": {
            "handler":
                c["handler"],

            "mode":
                c["mode"],

            "mission_completed":
                c[
                    "mission_completed"
                ],

            "passed":
                (
                    c["mode"]
                    == "RECOVERY_COMPLETE"
                    and c[
                        "mission_completed"
                    ]
                    is True
                ),
        },
    },

    "victim_agents_modified":
        False,
}


result["goal4_verified"] = all(
    item["passed"]
    for item in result[
        "tests"
    ].values()
)


(
    run_dir
    / "result.json"
).write_text(
    json.dumps(
        result,
        indent=2,
    )
)


manifest = {}

for path in sorted(
    p
    for p in run_dir.rglob("*")
    if (
        p.is_file()
        and p.name
        not in {
            "manifest.json",
            "manifest.sha256",
        }
    )
):
    digest = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()

    manifest[
        str(
            path.relative_to(
                run_dir
            )
        )
    ] = digest


(
    run_dir
    / "manifest.json"
).write_text(
    json.dumps(
        manifest,
        indent=2,
    )
)


with (
    run_dir
    / "manifest.sha256"
).open("w") as f:
    for name, digest in sorted(
        manifest.items()
    ):
        f.write(
            f"{digest}  {name}\n"
        )


if not result[
    "goal4_verified"
]:
    raise SystemExit(
        "GOAL #4 NOT VERIFIED."
    )


print()
print("========================================")
print("GOAL #4: VERIFIED")
print("SAFE_HOLD                  PASS")
print("REQUEST RECOVERY            PASS")
print("RESPONSE RECOVERY           PASS")
print("ENGINE UNCHANGED            PASS")
print("INPUTS UNCHANGED            PASS")
print("FROZEN VICTIMS              PASS")
print("NO CODE EDITS BETWEEN TESTS PASS")
print("========================================")
PY

if [ $? -ne 0 ]; then
  fail "Final Goal #4 evaluation failed."
fi

echo
echo "Evidence:"
echo "$RUN_DIR/result.json"
echo "$RUN_DIR/manifest.sha256"
