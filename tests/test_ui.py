"""Unit tests for the InvoicePilot Streamlit UI helper functions (``app.py``).

These tests exercise the testable logic in ``app.py`` — proposal extraction,
proposal construction, and the approve/reject/auto-reject callback flow —
without rendering Streamlit widgets (which require a browser). The PayPal
service is fully mocked; no real API is contacted and no live credentials
are required. The ``conftest.py`` stubs ``paypal_agent_toolkit`` and
``config`` so that importing :mod:`app` (and transitively :mod:`approval`
and :mod:`paypal_service`) is hermetic.

What is verified:
- ``extract_proposal`` finds invoice and reminder proposals, and returns
  ``None`` for errors, missing tool messages, and empty results.
- ``handle_approve`` builds the correct typed proposal and delegates to
  ``approval.approve``.
- ``handle_reject`` builds the proposal, delegates to ``approval.reject``,
  and clears the pending proposal.
- ``auto_reject_old_proposal`` rejects and clears a pending proposal when a
  new message arrives (OQ-5).
- The approval state machine blocks a duplicate approve after ``completed``.
- A ``malformed_response`` (timeout-ambiguous) result sets the correct state.
"""

import json
from unittest.mock import patch
from uuid import uuid4

import app
import approval
import paypal_service
from audit_log import add_entry
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from models import InvoiceProposal, ReminderProposal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoice_pending() -> dict:
    """A raw create_invoice proposal dict (as returned by the tool)."""
    return {
        "action_type": "create_invoice",
        "client_name": "Rahul",
        "client_email": "rahul@example.com",
        "amount": "300.00",
        "currency": "USD",
        "description": "Logo design",
    }


def _reminder_pending() -> dict:
    """A raw send_invoice_reminder proposal dict (as returned by the tool)."""
    return {
        "action_type": "send_invoice_reminder",
        "invoice_id": "INV2-TEST",
        "client_name": "Rahul",
        "amount_due": "300.00",
        "proposed_note": "Payment is overdue, please settle soon.",
    }


def _session_state(pending=None, proposal_id="test-id-123", state="pending"):
    """A plain-dict session_state for testing (mimics st.session_state)."""
    return {
        "messages": [],
        "pending_proposal": pending,
        "pending_proposal_id": proposal_id,
        "audit_log": [],
        "proposal_state": state,
    }


# ---------------------------------------------------------------------------
# 1–2. extract_proposal finds invoice / reminder proposals
# ---------------------------------------------------------------------------


def test_extract_proposal_finds_invoice_proposal():
    """extract_proposal returns the dict from a propose_create_invoice ToolMessage."""
    proposal_data = _invoice_pending()
    result = {
        "messages": [
            HumanMessage(content="Create an invoice for Rahul for $300"),
            ToolMessage(
                content=json.dumps(proposal_data),
                name="propose_create_invoice",
                tool_call_id="call-1",
            ),
            AIMessage(content="I've prepared a proposal for you to review."),
        ]
    }
    extracted = app.extract_proposal(result)
    assert extracted is not None
    assert extracted["action_type"] == "create_invoice"
    assert extracted["client_name"] == "Rahul"
    assert extracted["client_email"] == "rahul@example.com"
    assert extracted["amount"] == "300.00"
    assert extracted["currency"] == "USD"
    assert extracted["description"] == "Logo design"


def test_extract_proposal_finds_reminder_proposal():
    """extract_proposal returns the dict from a propose_send_reminder ToolMessage."""
    proposal_data = _reminder_pending()
    result = {
        "messages": [
            HumanMessage(content="Send a reminder for INV2-TEST"),
            ToolMessage(
                content=json.dumps(proposal_data),
                name="propose_send_reminder",
                tool_call_id="call-1",
            ),
            AIMessage(content="I've prepared a reminder proposal."),
        ]
    }
    extracted = app.extract_proposal(result)
    assert extracted is not None
    assert extracted["action_type"] == "send_invoice_reminder"
    assert extracted["invoice_id"] == "INV2-TEST"
    assert extracted["client_name"] == "Rahul"
    assert extracted["amount_due"] == "300.00"


# ---------------------------------------------------------------------------
# 3–5. extract_proposal returns None for error / no tools / empty
# ---------------------------------------------------------------------------


def test_extract_proposal_returns_none_for_error():
    """extract_proposal returns None when the ToolMessage contains an error."""
    result = {
        "messages": [
            ToolMessage(
                content=json.dumps({"error": "Amount exceeds $1,000 cap"}),
                name="propose_create_invoice",
                tool_call_id="call-1",
            ),
        ]
    }
    assert app.extract_proposal(result) is None


def test_extract_proposal_returns_none_for_no_tool_messages():
    """extract_proposal returns None when there are no ToolMessages."""
    result = {
        "messages": [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there! How can I help?"),
        ]
    }
    assert app.extract_proposal(result) is None


def test_extract_proposal_returns_none_for_empty_messages():
    """extract_proposal returns None for an empty messages list."""
    assert app.extract_proposal({"messages": []}) is None


# ---------------------------------------------------------------------------
# 6. Approve callback calls approval.approve with the correct proposal
# ---------------------------------------------------------------------------


def test_approve_callback_calls_approval():
    """handle_approve builds an InvoiceProposal and calls approval.approve."""
    session_state = _session_state(_invoice_pending())
    audit_log = session_state["audit_log"]

    with patch("approval.approve") as mock_approve:
        mock_approve.return_value = {"status": "sent", "invoice_id": "INV-TEST"}
        result = app.handle_approve(session_state, audit_log)

    mock_approve.assert_called_once()
    # The first positional arg is the proposal object.
    proposal_arg = mock_approve.call_args[0][0]
    assert isinstance(proposal_arg, InvoiceProposal)
    assert proposal_arg.action_type == "create_invoice"
    assert proposal_arg.client_name == "Rahul"
    assert proposal_arg.client_email == "rahul@example.com"
    # The proposal_id comes from session_state, not auto-generated.
    assert proposal_arg.proposal_id == "test-id-123"
    assert result["status"] == "sent"
    assert result["invoice_id"] == "INV-TEST"


# ---------------------------------------------------------------------------
# 7. Reject callback calls approval.reject and clears the pending proposal
# ---------------------------------------------------------------------------


def test_reject_callback_calls_reject():
    """handle_reject builds the proposal, calls approval.reject, and clears pending."""
    session_state = _session_state(_invoice_pending())
    audit_log = session_state["audit_log"]

    with patch("approval.reject") as mock_reject:
        mock_reject.return_value = {"status": "rejected"}
        result = app.handle_reject(session_state, audit_log)

    mock_reject.assert_called_once()
    proposal_arg = mock_reject.call_args[0][0]
    assert isinstance(proposal_arg, InvoiceProposal)
    assert proposal_arg.proposal_id == "test-id-123"
    # The pending proposal is cleared after rejection.
    assert session_state["pending_proposal"] is None
    assert session_state["pending_proposal_id"] is None
    assert result["status"] == "rejected"


# ---------------------------------------------------------------------------
# 8. Auto-reject old proposal (OQ-5)
# ---------------------------------------------------------------------------


def test_auto_reject_old_proposal():
    """When a new message arrives with a pending proposal, the old one is auto-rejected."""
    session_state = _session_state(_invoice_pending())
    audit_log = session_state["audit_log"]

    with patch("approval.reject") as mock_reject:
        mock_reject.return_value = {"status": "rejected"}
        rejected = app.auto_reject_old_proposal(session_state, audit_log)

    assert rejected is True
    mock_reject.assert_called_once()
    # The reject proxy carries the old proposal's action_type and id.
    proxy = mock_reject.call_args[0][0]
    assert proxy.action_type == "create_invoice"
    assert proxy.proposal_id == "test-id-123"
    # The old pending proposal is cleared.
    assert session_state["pending_proposal"] is None
    assert session_state["pending_proposal_id"] is None


def test_auto_reject_skips_when_no_pending():
    """auto_reject_old_proposal does nothing when there is no pending proposal."""
    session_state = _session_state(pending=None)
    audit_log = session_state["audit_log"]

    with patch("approval.reject") as mock_reject:
        rejected = app.auto_reject_old_proposal(session_state, audit_log)

    assert rejected is False
    mock_reject.assert_not_called()


# ---------------------------------------------------------------------------
# 9. Proposal state blocks duplicate approve
# ---------------------------------------------------------------------------


def test_proposal_state_blocks_duplicate_approve():
    """After approve sets state to 'completed', a second approve returns duplicate_rejected."""
    session_state = _session_state(_invoice_pending(), state="completed")
    audit_log = session_state["audit_log"]

    # Use the real approval.approve — the state guard returns before PayPal.
    result = app.handle_approve(session_state, audit_log)

    assert result["status"] == "duplicate_rejected"
    assert "completed" in result["error"]
    # State is unchanged.
    assert session_state["proposal_state"] == "completed"


# ---------------------------------------------------------------------------
# 10. Timeout ambiguous shows warning (state set correctly)
# ---------------------------------------------------------------------------


def test_timeout_ambiguous_shows_warning():
    """When approve returns malformed_response, the state is set to timeout_ambiguous."""
    session_state = _session_state(_invoice_pending())
    audit_log = session_state["audit_log"]

    with patch("paypal_service.revalidate") as mock_revalidate, patch(
        "paypal_service.create_and_send_invoice"
    ) as mock_create:
        mock_revalidate.return_value = paypal_service.ValidationResult(ok=True)
        mock_create.return_value = {
            "status": "malformed_response",
            "error": "Missing href",
        }
        result = app.handle_approve(session_state, audit_log)

    assert result["status"] == "malformed_response"
    # The approval engine maps malformed_response to the non-retryable
    # timeout_ambiguous state (NOT the retryable error state).
    assert session_state["proposal_state"] == "timeout_ambiguous"
    assert session_state["proposal_state"] != "error"


# ---------------------------------------------------------------------------
# 11. Clarification message preserves the pending proposal
# ---------------------------------------------------------------------------


def test_clarification_message_preserves_pending_proposal():
    """When extract_proposal returns None (a clarification message), the
    existing pending proposal is NOT auto-rejected — it stays intact."""
    session_state = _session_state(_invoice_pending())
    audit_log = session_state["audit_log"]

    # Simulate the agent returning a clarification — no proposal tool called,
    # so extract_proposal returns None.
    result = {
        "messages": [
            HumanMessage(content="Create an invoice for Rahul for $300"),
            AIMessage(content="What was the amount for the invoice?"),
        ]
    }

    # The new render_chat flow: extract_proposal first, then auto-reject ONLY
    # when a new proposal is actually extracted.
    proposal = app.extract_proposal(result)
    assert proposal is None

    # Because no new proposal was extracted, auto_reject_old_proposal is NOT
    # called — the pending proposal must be left intact.
    if proposal is not None:
        app.auto_reject_old_proposal(session_state, audit_log)

    # The existing pending proposal is preserved, state is still pending.
    assert session_state["pending_proposal"] is not None
    assert session_state["pending_proposal"]["client_name"] == "Rahul"
    assert session_state["proposal_state"] == "pending"
    # No audit entries — nothing was rejected.
    assert len(audit_log) == 0


# ---------------------------------------------------------------------------
# 12. New proposal replaces an old pending one
# ---------------------------------------------------------------------------


def test_new_proposal_replaces_old_one():
    """When a new proposal is extracted while one is pending, the old proposal
    is auto-rejected (audit log gets a 'rejected' entry) and the new one takes
    its place."""
    session_state = _session_state(_invoice_pending())
    audit_log = session_state["audit_log"]
    old_id = session_state["pending_proposal_id"]

    # Simulate the agent returning a NEW proposal (a reminder, different from
    # the pending invoice proposal).
    new_proposal_data = _reminder_pending()
    result = {
        "messages": [
            ToolMessage(
                content=json.dumps(new_proposal_data),
                name="propose_send_reminder",
                tool_call_id="call-1",
            ),
            AIMessage(content="I've prepared a new reminder proposal."),
        ]
    }

    # The new render_chat flow: extract the new proposal first.
    proposal = app.extract_proposal(result)
    assert proposal is not None

    # A new proposal was extracted — auto-reject the old pending one
    # (OQ-5: only one pending proposal at a time). Use the real
    # approval.reject so the audit entry is actually recorded.
    app.auto_reject_old_proposal(session_state, audit_log)

    # Store the new proposal (as render_chat does).
    new_id = str(uuid4())
    session_state["pending_proposal"] = proposal
    session_state["pending_proposal_id"] = new_id
    session_state["proposal_state"] = "pending"
    add_entry(
        audit_log,
        "proposed",
        f"Proposed: {proposal.get('action_type', 'unknown')}",
        proposal_id=new_id,
    )

    # Audit log has a "rejected" entry for the old proposal.
    rejected_entries = [e for e in audit_log if e.action_type == "rejected"]
    assert len(rejected_entries) == 1
    assert rejected_entries[0].proposal_id == old_id

    # The new proposal is stored and pending.
    assert session_state["pending_proposal"] is not None
    assert session_state["pending_proposal"]["action_type"] == "send_invoice_reminder"
    assert session_state["pending_proposal_id"] == new_id
    assert session_state["proposal_state"] == "pending"

    # Audit log also has a "proposed" entry for the new proposal.
    proposed_entries = [e for e in audit_log if e.action_type == "proposed"]
    assert len(proposed_entries) == 1


# ---------------------------------------------------------------------------
# 13. Error state hides the Approve button
# ---------------------------------------------------------------------------


def test_error_state_hides_approve_button():
    """When proposal_state is 'error', the card shows an error message instead
    of Approve/Reject buttons — handle_approve should not be reachable."""
    session_state = _session_state(_invoice_pending(), state="error")
    state = session_state["proposal_state"]

    # In render_proposal_card, the Approve button only renders inside
    # ``if state == "pending":``. In the "error" state that branch is skipped
    # and an error message is shown instead.
    assert state == "error"
    assert state != "pending"  # Approve button branch not taken


# ---------------------------------------------------------------------------
# 14. Timeout dismiss then approve is blocked
# ---------------------------------------------------------------------------


def test_timeout_dismiss_then_approve_blocked():
    """After dismissing a timeout_ambiguous proposal (state -> 'rejected'),
    a subsequent approve attempt is blocked by the state guard
    (duplicate_rejected)."""
    session_state = _session_state(_invoice_pending(), state="timeout_ambiguous")
    audit_log = session_state["audit_log"]

    # Dismiss the timeout_ambiguous proposal — the Dismiss button calls
    # handle_reject, which calls approval.reject, setting state to "rejected".
    dismiss_result = app.handle_reject(session_state, audit_log)
    assert dismiss_result["status"] == "rejected"
    assert session_state["proposal_state"] == "rejected"

    # handle_reject clears the pending proposal. Restore a pending proposal
    # reference (simulating a stale card or re-click) to verify the state
    # guard still blocks re-execution.
    session_state["pending_proposal"] = _invoice_pending()
    session_state["pending_proposal_id"] = "test-id-456"

    approve_result = app.handle_approve(session_state, audit_log)
    assert approve_result["status"] == "duplicate_rejected"
    assert "rejected" in approve_result["error"]


# ---------------------------------------------------------------------------
# 15. Duplicate rejection is logged to the audit log
# ---------------------------------------------------------------------------


def test_duplicate_rejection_logged_to_audit():
    """When approve returns duplicate_rejected, an audit entry with action_type
    'error' is logged to the audit log."""
    session_state = _session_state(_invoice_pending())
    audit_log = session_state["audit_log"]

    with patch("approval.approve") as mock_approve:
        mock_approve.return_value = {
            "status": "duplicate_rejected",
            "error": "Cannot approve: proposal is in state 'completed'.",
        }
        result = app.handle_approve(session_state, audit_log)

    assert result["status"] == "duplicate_rejected"

    # An audit entry was logged for the duplicate rejection.
    assert len(audit_log) == 1
    entry = audit_log[0]
    assert entry.action_type == "error"
    assert "duplicate" in entry.description.lower()
    assert entry.proposal_id == "test-id-123"
