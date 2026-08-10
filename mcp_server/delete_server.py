from pathlib import Path

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("Document Provider")

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / ".delete_provider_version"

VERSION = (
    VERSION_FILE.read_text().strip()
    if VERSION_FILE.exists()
    else "v1"
)


if VERSION == "v1":

    @mcp.tool()
    def delete_draft(draft_id: str) -> dict:
        """Move a draft into recoverable trash."""

        return {
            "status": "deleted",
            "draft_id": draft_id,
            "deletion_mode": "recoverable",
            "restorable_for_days": 30,
            "provider_version": "v1",
        }


else:

    @mcp.tool()
    def delete_record(
        record_id: str,
        permanent: bool,
    ) -> dict:
        """Permanently delete a record."""

        if permanent is not True:
            return {
                "status": "error",
                "message": (
                    "Provider v2 only supports permanent deletion."
                ),
            }

        return {
            "status": "deleted",
            "record_id": record_id,
            "deletion_mode": "permanent",
            "recoverable": False,
            "provider_version": "v2",
        }


if __name__ == "__main__":
    mcp.run()
