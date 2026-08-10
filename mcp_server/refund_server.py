from pathlib import Path

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("Refund Provider")

VERSION_FILE = Path(__file__).with_name(".provider_version")

VERSION = (
    VERSION_FILE.read_text().strip()
    if VERSION_FILE.exists()
    else "v1"
)


if VERSION == "v1":

    @mcp.tool()
    def refund_order(order_id: str, amount: float) -> dict:
        """Refund an order using the original v1 contract."""
        return {
            "status": "refunded",
            "order_id": order_id,
            "amount": amount,
            "currency": "USD",
            "provider_version": "v1",
        }


else:

    @mcp.tool()
    def issue_refund(
        purchase_ref: str,
        amount_minor_units: int,
        reason_code: str,
    ) -> dict:
        """Refund a purchase using the newer v2 contract."""

        allowed_reasons = {"RETURN", "DAMAGED", "FRAUD"}

        if reason_code not in allowed_reasons:
            return {
                "status": "error",
                "message": "Invalid reason_code",
                "allowed": sorted(allowed_reasons),
            }

        return {
            "status": "refunded",
            "purchase_ref": purchase_ref,
            "amount_minor_units": amount_minor_units,
            "currency": "USD",
            "reason_code": reason_code,
            "provider_version": "v2",
        }


if __name__ == "__main__":
    mcp.run()
