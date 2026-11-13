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

from config import PAYPAL_CLIENT_ID, PAYPAL_SECRET, PAYPAL_SELLER_EMAIL, PAYPAL_BUSINESS_NAME
from models import InvoiceProposal, ReminderProposal
from paypal_agent_toolkit.langchain.toolkit import PayPalToolkit
from paypal_agent_toolkit.shared.configuration import Configuration, Context

# ---------------------------------------------------------------------------
# Toolkit configuration (write actions only)
# ---------------------------------------------------------------------------

write_config = Configuration(
    actions={
        "invoices": {
            "create": True,        # create_invoice (may return DRAFT needing explicit send)
            "send": True,          # send_invoice for explicit DRAFT->SENT transition
            "sendReminder": True,  # send_invoice_reminder for reminders
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
    """Create and send a PayPal invoice.

    ACTUAL BEHAVIOR (verified from toolkit source and sandbox testing):
    - create_invoice POSTs to /v2/invoicing/invoices.
    - If PayPal returns a links-based response with the invoice ID, the toolkit
      handler auto-calls send_invoice and returns {createResult, sendResult}.
    - If the toolkit falls through (unexpected response shape), it returns the
      raw PayPal response which contains "id" and "links" directly.
      In that case the invoice is in DRAFT and we call send_invoice explicitly.

    Returns:
        {"status": "sent", "invoice_id": "<id>"} on success.
        {"status": "malformed_response", "error": ...} when the invoice was
            created but send failed with an ambiguous outcome.
        {"status": "error", "error": ...} on a pre-execution failure.
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
                    "quantity": "1",
                    "unit_amount": {
                        "currency_code": str(proposal.currency),
                        "value": str(proposal.amount),
                    },
                }
            ],
            "invoicer": {
                "business_name": PAYPAL_BUSINESS_NAME,
                **( {"email_address": PAYPAL_SELLER_EMAIL} if PAYPAL_SELLER_EMAIL else {}),
            },
        }
    )

    # Parse the tool response.
    try:
        create_result = json.loads(create_result_str) if isinstance(create_result_str, str) else create_result_str
    except (TypeError, ValueError):
        return {"status": "malformed_response", "error": f"Malformed response: {create_result_str}"}

    if not isinstance(create_result, dict):
        return {"status": "malformed_response", "error": f"Non-dict response: {create_result}"}

    # Path A: toolkit auto-sent the invoice and returned {createResult, sendResult}
    if "createResult" in create_result:
        create_inner = create_result["createResult"]
        if not isinstance(create_inner, dict) or "href" not in create_inner:
            return {"status": "malformed_response", "error": f"Missing href in createResult: {create_result}"}
        invoice_id = create_inner["href"].split("/")[-1]
        return {"status": "sent", "invoice_id": invoice_id}

    # Path B: toolkit returned the raw PayPal response (invoice in DRAFT).
    # Extract the invoice ID from the "id" field or from the links array.
    invoice_id = create_result.get("id")
    if not invoice_id:
        # Try extracting from the self link in the links array.
        for link in create_result.get("links", []):
            if link.get("rel") == "self" and "href" in link:
                invoice_id = link["href"].split("/")[-1]
                break

    if not invoice_id:
        return {"status": "malformed_response", "error": f"Cannot extract invoice ID from: {create_result}"}

    # Invoice exists in DRAFT — send it explicitly.
    send_result_str = write_tools["send_invoice"].invoke({"invoice_id": invoice_id})
    try:
        send_result = json.loads(send_result_str) if isinstance(send_result_str, str) else send_result_str
    except (TypeError, ValueError):
        send_result = send_result_str

    # PayPal returns HTTP 204 (empty body) on success; toolkit may return {} or empty string.
    send_str = str(send_result).lower()
    if "error" in send_str and "404" not in send_str and "400" not in send_str:
        # A real send error after a known invoice ID - keep Approve disabled.
        return {"status": "malformed_response", "error": f"Invoice {invoice_id} created but send failed: {send_result}"}

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
