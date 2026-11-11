"""Property-based test for the approval gate invariant (Task 8.2).

**Validates: Requirements 3.3, 3.5, 3.6**

Property 2: Approval_gate invariant
For ALL Approval_Card interactions, no gated PayPal write tool executes before
the Approve button is clicked exactly once. A double-click (two rapid Approve
calls) must not invoke PayPal twice — the second call is blocked as a duplicate
by the in-progress ("executing") guard.

The PayPal write tool is fully mocked — no real PayPal API is contacted.
"""

from decimal import Decimal
from unittest.mock import patch

from hypothesis import given, settings, strategies as st

import approval
import paypal_service
from models import InvoiceProposal


def _make_proposal() -> InvoiceProposal:
    """A valid InvoiceProposal for the approval-gate sequences."""
    return InvoiceProposal(
        client_name="Test",
        client_email="test@example.com",
        amount=Decimal("100"),
        description="Test",
    )


# Map each interaction set label to the number of Approve clicks it represents.
_CLICKS = {"nothing": 0, "approve_once": 1, "approve_twice": 2}


@given(
    st.lists(
        st.sampled_from(["nothing", "approve_once", "approve_twice"]),
        min_size=1,
        max_size=5,
    )
)
@settings(deadline=None, max_examples=100)
def test_approval_gate_invariant(actions):
    """No gated PayPal write tool is invoked unless Approve is clicked, and a
    double-click calls PayPal at most once per interaction set.

    **Validates: Requirements 3.3, 3.5, 3.6**
    """
    proposal = _make_proposal()

    for action_set in actions:
        session_state = {"proposal_state": "pending"}
        audit_log = []
        clicks = _CLICKS[action_set]

        with patch("paypal_service.revalidate") as r, patch(
            "paypal_service.create_and_send_invoice"
        ) as c:
            r.return_value = paypal_service.ValidationResult(ok=True)
            c.return_value = {"status": "sent", "invoice_id": "INV-TEST"}

            for _ in range(clicks):
                approval.approve(proposal, session_state, audit_log)

            # Invariant: PayPal is called 0 times with no Approve, and exactly
            # once with one or two Approve clicks (the double-click guard
            # blocks the second before any PayPal write).
            assert c.call_count == (0 if clicks == 0 else 1), (
                f"PayPal called {c.call_count} times for '{action_set}' "
                f"({clicks} clicks); expected {0 if clicks == 0 else 1}"
            )
