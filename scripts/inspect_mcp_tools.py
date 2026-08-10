import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp_server" / "refund_server.py"
VERSION_FILE = ROOT / "mcp_server" / ".provider_version"


async def main():
    version = VERSION_FILE.read_text().strip()

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

            print(f"Provider version: {version}")
            print("Available MCP tools:")
            for tool in result.tools:
                print(f"  - {tool.name}")


if __name__ == "__main__":
    asyncio.run(main())
