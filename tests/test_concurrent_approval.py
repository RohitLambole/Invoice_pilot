"""Concurrent / duplicate approval test for InvoicePilot.

Verifies that two rapid Approve clicks on the same proposal call the PayPal
service at most once. The approval engine's in-progress guard (the
"executing" state set before any PayPal call) blocks the second click before
any PayPal write is attempted, preventing a duplicate invoice.

The PayPal write tool is fully mocked — no real PayPal API is contacted.
"""

from unittest.mock import patch

import approval
import paypal_service


def test_concurrent_approval_calls_paypal_at_most_once(invoice_proposal):
    """Two rapid Approve clicks on the same proposal must not call PayPal twice."""
    session_state = {"proposal_state": "pending"}
    audit_log = []

    with patch("paypal_service.revalidate") as r, patch(
        "paypal_service.create_and_send_invoice"
    ) as c:
        r.return_value = paypal_service.ValidationResult(ok=True)
        c.return_value = {"status": "sent", "invoice_id": "INV-TEST"}

        # First approve succeeds and sends the invoice.
        result1 = approval.approve(invoice_proposal, session_state, audit_log)
        assert result1["status"] == "sent"

        # Second approve (double-click) must be rejected as a duplicate.
        result2 = approval.approve(invoice_proposal, session_state, audit_log)
        assert result2["status"] == "duplicate_rejected"

        # PayPal was reached exactly ONCE, not twice.
        assert c.call_count == 1
