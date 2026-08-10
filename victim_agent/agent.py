import sys
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters


SERVER_PATH = str(
    Path(__file__).resolve().parents[1]
    / "mcp_server"
    / "refund_server.py"
)


root_agent = LlmAgent(
    model="gemini-3.6-flash",
    name="refund_agent",
    description="A refund agent that uses the refund_order tool.",
    instruction="""
You are a refund processing agent.

When a user requests a refund, you MUST use the refund_order tool.

Never claim that a refund succeeded unless the tool itself returns
status='refunded'.

Do not invent refund confirmations.
""",
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable,
                    args=[SERVER_PATH],
                )
            ),
            tool_filter=["refund_order"],
        )
    ],
)
