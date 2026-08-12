import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}

    return json.loads(
        path.read_text()
    )


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []

    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def parse_time(value: str):
    return datetime.fromisoformat(
        value.replace(
            "Z",
            "+00:00",
        )
    )


def victim_ok(
    hash_file: str,
) -> bool:
    result = subprocess.run(
        [
            "sha256sum",
            "-c",
            hash_file,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    return (
        result.returncode
        == 0
    )


def matching_replay_event(
    events: list[dict],
    replay: dict,
):
    replay_id = replay.get(
        "replay_id"
    )

    matches = [
        event
        for event in events
        if event.get(
            "replay_id"
        )
        == replay_id
    ]

    return (
        matches[-1]
        if matches
        else None
    )


# ============================================================
# CONSEQUENTIAL REFUND EFFECT
# ============================================================

def probe_refund(
    scenario_dir: Path,
    plan: dict,
    replay: dict,
) -> dict:
    events = read_jsonl(
        ROOT
        / "mcp_server"
        / ".adapter_audit.jsonl"
    )

    records = load_json(
        ROOT
        / "mcp_server"
        / ".refund_records.json"
    )

    event = matching_replay_event(
        events,
        replay,
    )

    constraints = {
        item["field"]:
            item["expected_value"]
        for item in plan.get(
            "scope_constraints",
            [],
        )
    }

    order_id = constraints.get(
        "order_id"
    )

    amount = constraints.get(
        "amount"
    )

    expected_minor = (
        int(
            Decimal(
                str(amount)
            )
            * Decimal("100")
        )
        if amount is not None
        else None
    )

    expected_reason = next(
        (
            item.get("value")
            for item in plan.get(
                "operations",
                [],
            )
            if (
                item.get("operation")
                == "CONSTANT"
                and item.get(
                    "target_field"
                )
                == "reason_code"
            )
        ),
        None,
    )

    record = (
        records.get(order_id)
        if (
            isinstance(
                records,
                dict,
            )
            and order_id
        )
        else None
    )

    event_after_replay = bool(
        event
        and event.get(
            "recorded_at"
        )
        and replay.get(
            "started_at"
        )
        and parse_time(
            event["recorded_at"]
        )
        >= parse_time(
            replay["started_at"]
        )
    )

    checks = {
        "replay_linked_event_exists":
            event is not None,

        "event_after_replay_start":
            event_after_replay,

        "old_tool_correct":
            bool(
                event
                and event.get(
                    "old_tool"
                )
                == "refund_order"
            ),

        "new_tool_correct":
            bool(
                event
                and event.get(
                    "new_tool"
                )
                == "issue_refund"
            ),

        "compiled_purchase_ref_correct":
            bool(
                event
                and event.get(
                    "compiled_v2_args",
                    {},
                ).get(
                    "purchase_ref"
                )
                == order_id
            ),

        "compiled_amount_correct":
            bool(
                event
                and event.get(
                    "compiled_v2_args",
                    {},
                ).get(
                    "amount_minor_units"
                )
                == expected_minor
            ),

        "compiled_reason_correct":
            bool(
                event
                and event.get(
                    "compiled_v2_args",
                    {},
                ).get(
                    "reason_code"
                )
                == expected_reason
            ),

        "provider_record_exists":
            record is not None,

        "provider_is_v2":
            bool(
                record
                and record.get(
                    "provider_version"
                )
                == "v2"
            ),

        "provider_status_refunded":
            bool(
                record
                and record.get(
                    "status"
                )
                == "refunded"
            ),

        "victim_source_unchanged":
            victim_ok(
                "victim_agent.sha256"
            ),
    }

    verified = all(
        checks.values()
    )

    if verified:
        classification = (
            "VERIFIED_CONSEQUENTIAL_ACTION"
        )

    elif (
        event is None
        and record is None
    ):
        classification = (
            "NO_EFFECT_OBSERVED"
        )

    else:
        classification = (
            "EFFECT_UNCERTAIN"
        )

    return {
        "probe":
            "refund-consequential-action",

        "effect_class":
            classification,

        "effect_verified":
            verified,

        "checks":
            checks,

        "adapter_event":
            event,

        "provider_record":
            record,
    }


# ============================================================
# READ-ONLY SHIPMENT EXECUTION
# ============================================================

def probe_shipment(
    scenario_dir: Path,
    plan: dict,
    replay: dict,
) -> dict:
    events = read_jsonl(
        ROOT
        / "mcp_server"
        / ".shipment_adapter_audit.jsonl"
    )

    event = matching_replay_event(
        events,
        replay,
    )

    raw = (
        event.get(
            "raw_v2_response",
            {},
        )
        if event
        else {}
    )

    reconstructed = (
        event.get(
            "reconstructed_v1_response",
            {},
        )
        if event
        else {}
    )

    result = raw.get(
        "result",
        {}
    )

    shipment = result.get(
        "shipment",
        {}
    )

    event_after_replay = bool(
        event
        and event.get(
            "recorded_at"
        )
        and replay.get(
            "started_at"
        )
        and parse_time(
            event["recorded_at"]
        )
        >= parse_time(
            replay["started_at"]
        )
    )

    checks = {
        "replay_linked_event_exists":
            event is not None,

        "event_after_replay_start":
            event_after_replay,

        "old_tool_correct":
            bool(
                event
                and event.get(
                    "old_tool"
                )
                == "lookup_shipment"
            ),

        "new_tool_correct":
            bool(
                event
                and event.get(
                    "new_tool"
                )
                == "lookup_shipment"
            ),

        "native_v2_response_observed":
            bool(
                result
                and shipment
            ),

        "state_reconstructed":
            (
                result.get("state")
                == "in_transit"
                and reconstructed.get(
                    "status"
                )
                == "shipped"
            ),

        "tracking_reconstructed":
            (
                shipment.get(
                    "tracking_id"
                )
                is not None
                and reconstructed.get(
                    "tracking"
                )
                == shipment.get(
                    "tracking_id"
                )
            ),

        "carrier_reconstructed":
            (
                shipment.get(
                    "carrier_name"
                )
                is not None
                and reconstructed.get(
                    "carrier"
                )
                == shipment.get(
                    "carrier_name"
                )
            ),

        "eta_reconstructed":
            (
                shipment.get(
                    "estimated_delivery"
                )
                is not None
                and reconstructed.get(
                    "eta_date"
                )
                == shipment.get(
                    "estimated_delivery"
                )
            ),

        "victim_source_unchanged":
            victim_ok(
                "shipment_victim.sha256"
            ),
    }

    verified = all(
        checks.values()
    )

    if verified:
        classification = (
            "VERIFIED_READ_ONLY_EXECUTION"
        )

    elif event is None:
        classification = (
            "NO_EFFECT_OBSERVED"
        )

    else:
        classification = (
            "EFFECT_UNCERTAIN"
        )

    return {
        "probe":
            "shipment-read-only-execution",

        "effect_class":
            classification,

        "effect_verified":
            verified,

        "checks":
            checks,

        "adapter_event":
            event,
    }


@dataclass(frozen=True)
class EffectProbe:
    name: str
    old_tool: str
    new_tool: str
    requires_response_operations: bool | None
    runner: Callable


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


EFFECT_PROBES = (
    EffectProbe(
        name="refund-consequential-action",
        old_tool="refund_order",
        new_tool="issue_refund",
        requires_response_operations=False,
        runner=probe_refund,
    ),

    EffectProbe(
        name="shipment-read-only-execution",
        old_tool="lookup_shipment",
        new_tool="lookup_shipment",
        requires_response_operations=True,
        runner=probe_shipment,
    ),
)


def resolve_probe(
    plan: dict,
):
    matches = [
        probe
        for probe in EFFECT_PROBES
        if probe.matches(plan)
    ]

    if not matches:
        return None

    if len(matches) > 1:
        raise RuntimeError(
            "Ambiguous effect probe."
        )

    return matches[0]


def probe_scenario(
    scenario: str,
) -> dict:
    scenario_dir = (
        ROOT
        / "evidence"
        / "scenarios"
        / scenario
    )

    plan = load_json(
        scenario_dir
        / "repair-plan.json"
    )

    replay = load_json(
        scenario_dir
        / "replay-session.json"
    )

    if not plan:
        raise SystemExit(
            "STOP: repair plan missing."
        )

    if not replay:
        raise SystemExit(
            "STOP: replay session missing."
        )

    probe = resolve_probe(
        plan
    )

    if probe is None:
        result = {
            "scenario":
                scenario,

            "replay_id":
                replay.get(
                    "replay_id"
                ),

            "probe":
                None,

            "effect_class":
                "UNSUPPORTED_EFFECT_PROBE",

            "effect_verified":
                False,

            "checks":
                {},
        }

    else:
        result = probe.runner(
            scenario_dir,
            plan,
            replay,
        )

        result = {
            "scenario":
                scenario,

            "replay_id":
                replay.get(
                    "replay_id"
                ),

            **result,
        }

    output = (
        scenario_dir
        / "effect-probe.json"
    )

    output.write_text(
        json.dumps(
            result,
            indent=2,
        )
    )

    return result


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--scenario",
        required=True,
    )

    args = parser.parse_args()

    result = probe_scenario(
        args.scenario
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )

    print()
    print(
        "EFFECT:",
        result["effect_class"],
    )


if __name__ == "__main__":
    main()
