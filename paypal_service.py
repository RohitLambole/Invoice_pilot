"""PayPal write service for InvoicePilot (app-controlled).

This is the ONLY module with PayPal write-tool access. It is never imported
by ``agent.py`` or ``tools.py`` — the agent cannot reach these tools. Write
operations execute only after the Freelancer clicks Approve, routed through
the approval engine (:mod:`approval`).

Two write actions are enabled:
- ``create_invoice`` (auto-sends the invoice — spike-confirmed; no separate
  ``send_invoice`` call is made, which would send the invoice a second time).
- ``send_invoice_reminder`` (sends a payment reminder; supports an optional
  ``note`` parameter — spike-confirmed in spike_results.md section 3.5).

Never enabled: ``cancel``, ``generateQRC``, and all order/subscription tools.
``delete_invoice`` does not exist in ``paypal-agent-toolkit==1.1.0``.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal

from config import PAYPAL_CLIENT_ID, PAYPAL_SECRET
from models import InvoiceProposal, ReminderProposal
from paypal_agent_toolkit.langchain.toolkit import PayPalToolkit
from paypal_agent_toolkit.shared.configuration import Configuration, Context

# ---------------------------------------------------------------------------
# Toolkit configuration (write actions only)
# ---------------------------------------------------------------------------

write_config = Configuration(
    actions={
        "invoices": {
            "create": True,        # create_invoice auto-sends (spike-confirmed)
            "sendReminder": True,   # send_invoice_reminder for reminders
            # "send" is omitted: create_invoice already sends the invoice; a
            # separate send_invoice would dispatch a duplicate. Enable only
            # if a DRAFT->SENT transition is ever needed.
        }
    },
    context=Context(sandbox=True),
)

write_toolkit = PayPalToolkit(
    client_id=PAYPAL_CLIENT_ID,
    secret=PAYPAL_SECRET,
    configuration=write_config,
)

# Map tool.name -> tool for lookup by name (spike-confirmed names:
# "create_invoice", "send_invoice_reminder").
write_tools = {t.name: t for t in write_toolkit.get_tools()}


# ---------------------------------------------------------------------------
# Revalidation result (defense in depth before any PayPal write)
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of revalidating a proposal before execution.

    Attributes:
        ok: True if the proposal passed all checks.
        error: Human-readable error message when ``ok`` is False, else None.
    """

    ok: bool
    error: str | None = None


# Simplified RFC 5322 email pattern (mirrors models._EMAIL_RE).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Amount cap as Decimal for exact comparison (mirrors config.AMOUNT_CAP).
AMOUNT_CAP = Decimal("1000.00")


def revalidate(proposal) -> ValidationResult:
    """Revalidate a proposal before execution (defense in depth).

    The Pydantic models already validate at construction time; this function
    re-checks just before the PayPal call so that a stale or tampered proposal
    can never slip through.

    For ``create_invoice`` proposals: validates amount (0 < amount <= 1000),
    currency == USD, and email format.
    For ``send_invoice_reminder`` proposals: validates amount_due > 0.
    """
    if proposal.action_type == "create_invoice":
        if proposal.amount <= 0:
            return ValidationResult(
                False, f"Amount must be greater than 0, got {proposal.amount}"
            )
        if proposal.amount > AMOUNT_CAP:
            return ValidationResult(
                False, f"Amount exceeds $1,000 cap, got {proposal.amount}"
            )
        if proposal.currency != "USD":
            return ValidationResult(
                False, f"Currency must be USD, got {proposal.currency}"
            )
        if not _EMAIL_RE.match(proposal.client_email):
            return ValidationResult(
                False, f"Invalid email format: {proposal.client_email}"
            )
    elif proposal.action_type == "send_invoice_reminder":
        if proposal.amount_due <= 0:
            return ValidationResult(
                False,
                f"Amount due must be greater than 0, got {proposal.amount_due}",
            )
    return ValidationResult(True)


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


def create_and_send_invoice(proposal: InvoiceProposal) -> dict:
    """Create and send a PayPal invoice in a single call.

    SPIKE-CONFIRMED (spike_results.md section 3.3):
    - ``create_invoice`` auto-sends the invoice. Do NOT call ``send_invoice``
      separately — it would send the invoice a second time.
    - Recipient email goes in ``primary_recipients[0].billing_info.email_address``
      (NOT a top-level ``recipient_email`` field).
    - ``quantity`` must be a string, not int.
    - ``unit_amount`` uses ``currency_code`` and string values.
    - Invoice ID is parsed from ``createResult.href.split("/")[-1]`` (NOT from
      a top-level ``id`` field).

    Returns:
        ``{"status": "sent", "invoice_id": "<id>"}`` on success.
        ``{"status": "malformed_response", "error": ...}`` when the PayPal
            write was attempted but the response cannot be parsed or lacks the
            expected structure. The outcome is unknown — the caller treats this
            as non-retryable (timeout_ambiguous).
        ``{"status": "error", "error": ...}`` on a pre-execution failure (e.g.
            the tool call itself raised before any PayPal write).
    """
    create_result_str = write_tools["create_invoice"].invoke(
        {
            "detail": {"currency_code": str(proposal.currency)},
            "primary_recipients": [
                {
                    "billing_info": {
                        "email_address": proposal.client_email,
                    }
                }
            ],
            "items": [
                {
                    "name": proposal.description,
                    "quantity": "1",  # string, confirmed by spike
                    "unit_amount": {
                        "currency_code": str(proposal.currency),
                        "value": str(proposal.amount),  # string repr of Decimal
                    },
                }
            ],
        }
    )

    # Tool returns a JSON string; parse it.
    try:
        create_result = json.loads(create_result_str)
    except (TypeError, ValueError):
        return {
            "status": "malformed_response",
            "error": f"Malformed response: {create_result_str}",
        }

    # Validate expected structure before accessing nested fields.
    if not isinstance(create_result, dict) or "createResult" not in create_result:
        return {
            "status": "malformed_response",
            "error": f"Unexpected response structure: {create_result}",
        }

    create_inner = create_result["createResult"]
    if not isinstance(create_inner, dict) or "href" not in create_inner:
        return {
            "status": "malformed_response",
            "error": f"Missing href in createResult: {create_result}",
        }

    # Parse invoice ID from href (spike_results.md section 3.2).
    invoice_id = create_inner["href"].split("/")[-1]

    # create_invoice already sent — no separate send_invoice call.
    return {"status": "sent", "invoice_id": invoice_id}


def send_reminder(invoice_id: str, proposed_note: str | None = None) -> dict:
    """Send a payment reminder for an existing invoice.

    SPIKE-CONFIRMED (spike_results.md section 3.5):
    ``send_invoice_reminder`` accepts an optional ``note`` field.
    ``proposed_note`` from ``ReminderProposal`` is safe to pass directly.

    Returns:
        ``{"status": "sent"}`` on success.
        ``{"status": "error", "error": ...}`` on failure.
    """
    payload: dict = {"invoice_id": invoice_id}
    if proposed_note:
        payload["note"] = proposed_note  # confirmed supported by spike

    result_str = write_tools["send_invoice_reminder"].invoke(payload)

    try:
        result = (
            json.loads(result_str) if isinstance(result_str, str) else result_str
        )
    except (TypeError, ValueError):
        return {"status": "error", "error": f"Malformed response: {result_str}"}

    if isinstance(result, dict) and "error" in result:
        return {"status": "error", "error": str(result)}

    return {"status": "sent"}


__all__ = [
    "create_and_send_invoice",
    "send_reminder",
    "revalidate",
    "ValidationResult",
]
