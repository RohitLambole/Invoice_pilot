"""Property-based test for the audit log completeness invariant (Task 4.2).

**Validates: Requirements 6.1, 6.2, 6.5**

Property 4: Audit_Log completeness invariant
For ALL sequences of proposals, approvals, rejections, and executions, every
proposal has a "proposed" entry, every approval an "approved" entry, every
rejection a "rejected" entry, and every execution an "executed" or "error"
entry in the audit log.

The PayPal service is fully mocked — no real PayPal API is contacted.
"""

from decimal import Decimal
from unittest.mock import patch

from hypothesis import given, settings, strategies as st

import approval
import paypal_service
from audit_log import add_entry
from models import InvoiceProposal


def _make_proposal() -> InvoiceProposal:
    """A valid InvoiceProposal for the audit-completeness sequences."""
    return InvoiceProposal(
        client_name="Test",
        client_email="test@example.com",
        amount=Decimal("100"),
        description="Test",
    )


@given(
    st.lists(
        st.sampled_from(["propose", "approve_sent", "approve_error", "reject"]),
        min_size=1,
        max_size=20,
    )
)
@settings(deadline=None, max_examples=100)
def test_audit_log_completeness(actions):
    """Every action in a random sequence produces the expected audit entry,
    and every entry is correlated to the proposal via proposal_id.

    **Validates: Requirements 6.1, 6.2, 6.5**
    """
    proposal = _make_proposal()
    session_state = {"proposal_state": "pending"}
    audit_log = []

    n_propose = 0
    n_approve_sent = 0
    n_approve_error = 0
    n_reject = 0

    for action in actions:
        if action == "propose":
            add_entry(
                audit_log,
                "proposed",
                "Proposed",
                proposal_id=proposal.proposal_id,
            )
            n_propose += 1
        elif action == "approve_sent":
            # Reset to a fresh pending state so each approve runs the full flow.
            session_state["proposal_state"] = "pending"
            with patch("paypal_service.revalidate") as r, patch(
                "paypal_service.create_and_send_invoice"
            ) as c:
                r.return_value = paypal_service.ValidationResult(ok=True)
                c.return_value = {"status": "sent", "invoice_id": "INV-TEST"}
                approval.approve(proposal, session_state, audit_log)
            n_approve_sent += 1
        elif action == "approve_error":
            session_state["proposal_state"] = "pending"
            with patch("paypal_service.revalidate") as r, patch(
                "paypal_service.create_and_send_invoice"
            ) as c:
                r.return_value = paypal_service.ValidationResult(ok=True)
                c.return_value = {"status": "error", "error": "test"}
                approval.approve(proposal, session_state, audit_log)
            n_approve_error += 1
        elif action == "reject":
            approval.reject(proposal, session_state, audit_log)
            n_reject += 1

    # Count audit entries by action type.
    counts = {"proposed": 0, "approved": 0, "rejected": 0, "executed": 0, "error": 0}
    for entry in audit_log:
        counts[entry.action_type] = counts.get(entry.action_type, 0) + 1

    # Completeness: each action type produces exactly the right number of
    # corresponding audit entries.
    # - propose    -> one "proposed" entry
    # - approve_sent  -> one "approved" + one "executed"
    # - approve_error -> one "approved" + one "error"
    # - reject     -> one "rejected" entry
    assert counts["proposed"] == n_propose
    assert counts["approved"] == n_approve_sent + n_approve_error
    assert counts["executed"] == n_approve_sent
    assert counts["error"] == n_approve_error
    assert counts["rejected"] == n_reject

    # Correlation: every entry carries the proposal_id.
    for entry in audit_log:
        assert entry.proposal_id == proposal.proposal_id
