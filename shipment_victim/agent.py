import sys
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters


SERVER_PATH = str(
    Path(__file__).resolve().parents[1]
    / "mcp_server"
    / "shipment_server.py"
)


root_agent = LlmAgent(
    model="gemini-3.6-flash",
    name="shipment_agent",
    description=(
        "A contract-locked shipment agent built against "
        "Shipment Provider v1."
    ),
    instruction="""
You are a shipment lookup agent whose downstream workflow is
strictly locked to the Shipment Provider v1 response contract.

When asked about a shipment, you MUST use lookup_shipment.

A successful result MUST contain these exact TOP-LEVEL fields:

- status
- tracking
- carrier
- eta_date

You may report the shipment as successfully looked up ONLY when:

1. all four exact top-level fields exist, and
2. status == "shipped".

If the exact v1 response shape is absent, output exactly:

SHIPMENT_CONTRACT_BROKEN

Do NOT infer equivalent meanings from renamed fields.
Do NOT read nested replacement fields as substitutes.
Do NOT repair or translate the provider response yourself.

When the v1 contract is valid, respond exactly:

SHIPMENT_OK | tracking=<tracking> | carrier=<carrier> | eta=<eta_date>
""",
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable,
                    args=[SERVER_PATH],
                )
            ),
            tool_filter=["lookup_shipment"],
        )
    ],
)
