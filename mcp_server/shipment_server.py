import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from toolsuture.compat_runtime import (
    CompatibilityRuntimeError,
    adapt_response,
    compile_request,
)


mcp = FastMCP("Shipment Provider")


VERSION_FILE = (
    ROOT / ".shipment_provider_version"
)

ADAPTER_FILE = (
    ROOT / ".deployed_adapter.json"
)

AUDIT_FILE = (
    ROOT / ".shipment_adapter_audit.jsonl"
)

REPLAY_CONTEXT_FILE = (
    ROOT / ".shipment_replay_context.json"
)


VERSION = (
    VERSION_FILE.read_text().strip()
    if VERSION_FILE.exists()
    else "v1"
)


class ShipmentV1(BaseModel):
    status: str
    tracking: str
    carrier: str
    eta_date: str


class ShipmentDetailsV2(BaseModel):
    tracking_id: str
    carrier_name: str
    estimated_delivery: str


class ShipmentResultV2(BaseModel):
    state: str
    shipment: ShipmentDetailsV2


class ShipmentV2(BaseModel):
    result: ShipmentResultV2


def lookup_shipment_v2_impl(
    tracking_id: str,
) -> ShipmentV2:
    return ShipmentV2(
        result=ShipmentResultV2(
            state="in_transit",
            shipment=ShipmentDetailsV2(
                tracking_id=tracking_id,
                carrier_name="Northstar Parcel",
                estimated_delivery="2026-08-14",
            ),
        )
    )


def append_audit(event: dict) -> None:
    with AUDIT_FILE.open("a") as f:
        f.write(
            json.dumps(event)
            + "\n"
        )


def read_replay_context() -> dict:
    if not REPLAY_CONTEXT_FILE.exists():
        return {}

    return json.loads(
        REPLAY_CONTEXT_FILE.read_text()
    )


def active_shipment_plan():
    if not ADAPTER_FILE.exists():
        return None

    deployment = json.loads(
        ADAPTER_FILE.read_text()
    )

    if deployment.get("status") != "ACTIVE":
        return None

    plan = deployment.get("plan", {})

    if (
        plan.get("old_tool")
        != "lookup_shipment"
        or plan.get("new_tool")
        != "lookup_shipment"
    ):
        return None

    return plan


if VERSION == "v1":

    @mcp.tool()
    def lookup_shipment(
        tracking_id: str,
    ) -> ShipmentV1:
        """Look up shipment using the original v1 contract."""

        return ShipmentV1(
            status="shipped",
            tracking=tracking_id,
            carrier="Northstar Parcel",
            eta_date="2026-08-14",
        )


else:

    deployed_plan = active_shipment_plan()

    if deployed_plan is None:

        @mcp.tool()
        def lookup_shipment(
            tracking_id: str,
        ) -> ShipmentV2:
            """Native Shipment Provider v2 interface."""

            return lookup_shipment_v2_impl(
                tracking_id
            )

    else:

        @mcp.tool()
        def lookup_shipment(
            tracking_id: str,
        ) -> ShipmentV1:
            """
            ToolSuture compatibility interface.

            The provider still executes the real v2 capability,
            but ToolSuture reconstructs the frozen consumer's
            original v1 response contract.
            """

            old_args = {
                "tracking_id": tracking_id,
            }

            try:
                new_args = compile_request(
                    old_args,
                    deployed_plan,
                )

                if set(new_args) != {
                    "tracking_id"
                }:
                    raise CompatibilityRuntimeError(
                        "Compiled request does not match "
                        "Shipment Provider v2 input contract."
                    )

                raw_v2 = (
                    lookup_shipment_v2_impl(
                        tracking_id=new_args[
                            "tracking_id"
                        ]
                    )
                )

                raw_v2_dict = (
                    raw_v2.model_dump(
                        mode="json"
                    )
                )

                reconstructed = adapt_response(
                    raw_v2_dict,
                    deployed_plan,
                )

                restored_v1 = (
                    ShipmentV1.model_validate(
                        reconstructed
                    )
                )

                append_audit({
                    "recorded_at":
                        datetime.now(
                            timezone.utc
                        ).isoformat(),

                    "replay_id":
                        read_replay_context().get(
                            "replay_id"
                        ),

                    "scenario":
                        "response-reshape",

                    "old_tool":
                        deployed_plan[
                            "old_tool"
                        ],

                    "new_tool":
                        deployed_plan[
                            "new_tool"
                        ],

                    "old_args":
                        old_args,

                    "compiled_v2_args":
                        new_args,

                    "raw_v2_response":
                        raw_v2_dict,

                    "reconstructed_v1_response":
                        restored_v1.model_dump(
                            mode="json"
                        ),

                    "scope":
                        deployed_plan[
                            "scope"
                        ],
                })

                return restored_v1

            except CompatibilityRuntimeError:
                raise


if __name__ == "__main__":
    mcp.run()
