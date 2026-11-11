"""Custom LangChain proposal tools for InvoicePilot.

Provides three LangChain-compatible tools that the agent calls to produce
structured proposals. These tools validate inputs but do NOT execute any
PayPal operation. They never write to ``clients.json`` or call any PayPal API.

The tools return JSON strings (not Python dicts) because LangChain serialises
tool return values into ``ToolMessage.content`` as strings.

This module deliberately does NOT import :mod:`config` or
:mod:`paypal_service`:
- ``config`` fails fast when ``.env`` secrets are missing, and these tools
  must remain importable (and unit-testable) without credentials present.
- ``paypal_service`` is the gated write layer; importing it here would break
  the agent/security boundary — the agent must never hold write tools.

Security boundary: these tools are registered with the LangChain agent
(``agent.py``). They are read-only / proposal-only. The agent can never
escalate to a PayPal write through them.
"""

import json
import re
from decimal import ROUND_HALF_UP, Decimal

from langchain_core.tools import tool

from client_registry import load_clients, lookup_email

# ---------------------------------------------------------------------------
# Local constants (not imported from config to avoid the .env fail-fast;
# mirror config.AMOUNT_CAP and models.AMOUNT_CAP).
# ---------------------------------------------------------------------------

#: Maximum invoice amount in USD. Mirrors ``config.AMOUNT_CAP``.
AMOUNT_CAP = Decimal("1000.00")

#: The only supported currency.
CURRENCY = "USD"

#: Simplified RFC 5322 email pattern: ``local@domain.tld`` with no whitespace
#: or additional ``@`` symbols. Mirrors ``models._EMAIL_RE``.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@tool
def lookup_client_email(client_name: str) -> str:
    """Look up a client's email address by name in clients.json.
    Returns the email if found, or an error JSON if not found.
    This tool is read-only. It never writes to clients.json or calls PayPal.

    Args:
        client_name: The exact name of the client to look up.
    """
    clients = load_clients()
    email = lookup_email(client_name, clients)
    if email is None:
        return json.dumps(
            {
                "error": (
                    f"Client not found: {client_name}. "
                    f"Ask the user for the email address."
                )
            }
        )
    return json.dumps({"client_name": client_name, "client_email": email})


@tool
def propose_create_invoice(
    client_name: str,
    client_email: str,
    amount: float,
    description: str,
) -> str:
    """Propose creating a new PayPal invoice. Does NOT create or send the
    invoice. Returns a structured JSON proposal for the user to approve.

    Args:
        client_name: Name of the client to invoice.
        client_email: Email address to send the invoice to.
        amount: Invoice amount in USD. Must be greater than 0 and at most 1000.
        description: Description of the work or service.
    """
    # Convert to Decimal for exact monetary arithmetic and validation.
    amount_decimal = Decimal(str(amount))

    # Validate amount: must be > 0 (Requirement 2.1).
    if amount_decimal <= 0:
        return json.dumps(
            {"error": f"Amount must be greater than 0, got {amount}"}
        )
    # Validate amount: must not exceed the $1,000 cap (Requirement 2.1).
    if amount_decimal > AMOUNT_CAP:
        return json.dumps(
            {"error": f"Amount exceeds $1,000 cap, got ${amount}"}
        )

    # Validate email format (simplified RFC 5322).
    if not _EMAIL_RE.match(client_email):
        return json.dumps({"error": f"Invalid email: {client_email}"})

    # Quantise to 2 decimal places for exact monetary representation.
    amount_decimal = amount_decimal.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    proposal = {
        "action_type": "create_invoice",
        "client_name": client_name,
        "client_email": client_email,
        "amount": str(amount_decimal),  # serialise as string to preserve precision
        "currency": CURRENCY,
        "description": description,
    }
    return json.dumps(proposal)


@tool
def propose_send_reminder(
    invoice_id: str,
    client_name: str,
    amount_due: float,
    proposed_note: str = "",
) -> str:
    """Propose sending a payment reminder for an overdue invoice.
    Does NOT send the reminder. Returns a structured JSON proposal.

    Args:
        invoice_id: PayPal invoice ID of the overdue invoice.
        client_name: Name of the client.
        amount_due: Amount still owed on the invoice.
        proposed_note: Optional message shown to the Freelancer on the approval
            card. This is a PREVIEW only. Whether PayPal sends a custom note is
            unverified — see paypal_service.send_reminder for details.
    """
    amount_decimal = Decimal(str(amount_due)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    proposal = {
        "action_type": "send_invoice_reminder",
        "invoice_id": invoice_id,
        "client_name": client_name,
        "amount_due": str(amount_decimal),
        "proposed_note": proposed_note,
    }
    return json.dumps(proposal)


__all__ = [
    "lookup_client_email",
    "propose_create_invoice",
    "propose_send_reminder",
]
