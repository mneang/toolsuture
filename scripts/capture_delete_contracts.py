import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]

SERVER = (
    ROOT
    / "mcp_server"
    / "delete_server.py"
)

VERSION_FILE = (
    ROOT
    / "mcp_server"
    / ".delete_provider_version"
)

SCENARIO = (
    ROOT
    / "evidence"
    / "scenarios"
    / "destructive-delete"
)


async def capture(version, filename):
    VERSION_FILE.write_text(version)

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.list_tools()

            data = {
                "provider_version": version,
                "tools": [
                    tool.model_dump(
                        by_alias=True,
                        exclude_none=True,
                        mode="json",
                    )
                    for tool in result.tools
                ],
            }

            path = SCENARIO / filename

            path.write_text(
                json.dumps(data, indent=2)
            )

            print(version)

            for tool in result.tools:
                print(" -", tool.name)


async def main():
    await capture(
        "v1",
        "old-contract.json",
    )

    await capture(
        "v2",
        "new-contract.json",
    )

    VERSION_FILE.write_text("v2")


if __name__ == "__main__":
    asyncio.run(main())
