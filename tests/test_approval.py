"""Unit tests for the InvoicePilot approval engine (:mod:`approval`).

These tests exercise the approval state machine in isolation. The PayPal
service is fully mocked — no real PayPal API is ever contacted. The
``conftest.py`` stubs the PayPal toolkit and ``config`` so that importing
:mod:`approval` (and transitively :mod:`paypal_service`) is hermetic and does
not require live credentials.

State machine under test::

    PENDING -> EXECUTING -> COMPLETED | TIMEOUT_AMBIGUOUS | ERROR
    PENDING -> REJECTED

Failure semantics:
    - "error"             -> definite pre-execution failure; retryable.
    - "timeout_ambiguous" -> PayPal write was attempted, outcome unknown;
      NON-retryable (a second Approve could create a duplicate invoice).
"""

from unittest.mock import patch

import approval
import paypal_service


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_approve_success(invoice_proposal):
    """Approve a pending proposal: PayPal send succeeds, state -> completed."""
    session_state = {"proposal_state": "pending"}
    audit_log = []

    with patch("paypal_service.revalidate") as mock_revalidate, patch(
        "paypal_service.create_and_send_invoice"
    ) as mock_create:
        mock_revalidate.return_value = paypal_service.ValidationResult(ok=True)
        mock_create.return_value = {"status": "sent", "invoice_id": "INV2-TEST"}

        result = approval.approve(invoice_proposal, session_state, audit_log)

    assert result["status"] == "sent"
    assert result["invoice_id"] == "INV2-TEST"
    assert session_state["proposal_state"] == "completed"

    # Audit log: an "approved" entry followed by an "executed" entry, both
    # correlated to this proposal's id.
    assert len(audit_log) == 2
    assert audit_log[0].action_type == "approved"
    assert audit_log[1].action_type == "executed"
    assert audit_log[0].proposal_id == invoice_proposal.proposal_id
    assert audit_log[1].proposal_id == invoice_proposal.proposal_id


# ---------------------------------------------------------------------------
# Duplicate / in-progress guard
# ---------------------------------------------------------------------------


def test_duplicate_rejected_executing(invoice_proposal):
    """A proposal already executing must not be re-approved (double-click race)."""
    session_state = {"proposal_state": "executing"}
    audit_log = []

    with patch("paypal_service.create_and_send_invoice") as mock_create:
        result = approval.approve(invoice_proposal, session_state, audit_log)

    assert result["status"] == "duplicate_rejected"
    assert "executing" in result["error"]
    # State unchanged; PayPal never touched.
    assert session_state["proposal_state"] == "executing"
    mock_create.assert_not_called()


def test_duplicate_rejected_completed(invoice_proposal):
    """An already-completed proposal must not be re-approved."""
    session_state = {"proposal_state": "completed"}
    audit_log = []

    with patch("paypal_service.create_and_send_invoice") as mock_create:
        result = approval.approve(invoice_proposal, session_state, audit_log)

    assert result["status"] == "duplicate_rejected"
    assert "completed" in result["error"]
    assert session_state["proposal_state"] == "completed"
    mock_create.assert_not_called()


def test_duplicate_rejected_timeout_ambiguous(invoice_proposal):
    """CRITICAL: an outcome-unknown proposal must not be re-approved.

    A second Approve here could create a duplicate invoice because the first
    PayPal write's result is unknown.
    """
    session_state = {"proposal_state": "timeout_ambiguous"}
    audit_log = []

    with patch("paypal_service.create_and_send_invoice") as mock_create:
        result = approval.approve(invoice_proposal, session_state, audit_log)

    assert result["status"] == "duplicate_rejected"
    assert "timeout_ambiguous" in result["error"]
    assert session_state["proposal_state"] == "timeout_ambiguous"
    mock_create.assert_not_called()


def test_duplicate_rejected_rejected(invoice_proposal):
    """A rejected proposal must not be re-approved; a fresh proposal is required."""
    session_state = {"proposal_state": "rejected"}
    audit_log = []

    with patch("paypal_service.create_and_send_invoice") as mock_create:
        result = approval.approve(invoice_proposal, session_state, audit_log)

    assert result["status"] == "duplicate_rejected"
    assert "rejected" in result["error"]
    assert session_state["proposal_state"] == "rejected"
    mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# Revalidation failure
# ---------------------------------------------------------------------------


def test_revalidation_failure(invoice_proposal):
    """A failed revalidation aborts before PayPal and sets the retryable error state."""
    session_state = {"proposal_state": "pending"}
    audit_log = []

    with patch("paypal_service.revalidate") as mock_revalidate, patch(
        "paypal_service.create_and_send_invoice"
    ) as mock_create:
        mock_revalidate.return_value = paypal_service.ValidationResult(
            ok=False, error="Amount exceeds cap"
        )

        result = approval.approve(invoice_proposal, session_state, audit_log)

    assert result["status"] == "error"
    assert result["error"] == "Amount exceeds cap"
    # Retryable: definite pre-execution failure (no PayPal write attempted).
    assert session_state["proposal_state"] == "error"
    mock_create.assert_not_called()

    # An "error" audit entry correlated to the proposal.
    assert len(audit_log) == 1
    assert audit_log[0].action_type == "error"
    assert audit_log[0].proposal_id == invoice_proposal.proposal_id


# ---------------------------------------------------------------------------
# Malformed response (non-retryable)
# ---------------------------------------------------------------------------


def test_malformed_response_sets_timeout_ambiguous(invoice_proposal):
    """A malformed PayPal response must set timeout_ambiguous, NOT error.

    The PayPal write was attempted, so the outcome is unknown and a second
    Approve is non-retryable.
    """
    session_state = {"proposal_state": "pending"}
    audit_log = []

    with patch("paypal_service.revalidate") as mock_revalidate, patch(
        "paypal_service.create_and_send_invoice"
    ) as mock_create:
        mock_revalidate.return_value = paypal_service.ValidationResult(ok=True)
        mock_create.return_value = {"status": "malformed_response", "error": "Missing href"}

        result = approval.approve(invoice_proposal, session_state, audit_log)

    assert result["status"] == "malformed_response"
    assert session_state["proposal_state"] == "timeout_ambiguous"
    # Explicitly: this is NOT the retryable "error" state.
    assert session_state["proposal_state"] != "error"

    # The approval was logged, then an "error" entry for the malformed outcome.
    assert any(e.action_type == "approved" for e in audit_log)
    assert any(e.action_type == "error" for e in audit_log)


# ---------------------------------------------------------------------------
# Definite error (retryable)
# ---------------------------------------------------------------------------


def test_error_sets_error_state(invoice_proposal):
    """A definite pre-execution error (e.g. auth) sets the retryable error state."""
    session_state = {"proposal_state": "pending"}
    audit_log = []

    with patch("paypal_service.revalidate") as mock_revalidate, patch(
        "paypal_service.create_and_send_invoice"
    ) as mock_create:
        mock_revalidate.return_value = paypal_service.ValidationResult(ok=True)
        mock_create.return_value = {"status": "error", "error": "Auth failed"}

        result = approval.approve(invoice_proposal, session_state, audit_log)

    assert result["status"] == "error"
    # Retryable: the PayPal write itself failed before any invoice was created.
    assert session_state["proposal_state"] == "error"


# ---------------------------------------------------------------------------
# Reject flow
# ---------------------------------------------------------------------------


def test_reject_sets_rejected_state(invoice_proposal):
    """Reject sets the proposal state to rejected and logs the event."""
    session_state = {"proposal_state": "pending"}
    audit_log = []

    result = approval.reject(invoice_proposal, session_state, audit_log)

    assert result["status"] == "rejected"
    assert session_state["proposal_state"] == "rejected"
    assert len(audit_log) == 1
    assert audit_log[0].action_type == "rejected"
    assert audit_log[0].proposal_id == invoice_proposal.proposal_id


def test_reject_after_timeout_blocks_reapprove(invoice_proposal):
    """After a timeout-ambiguous proposal is rejected, Approve stays blocked.

    Reject only dismisses the card; it does not resolve the unknown PayPal
    transaction. A subsequent Approve must be rejected as a duplicate rather
    than re-executing PayPal.
    """
    session_state = {"proposal_state": "timeout_ambiguous"}
    audit_log = []

    # Reject the ambiguous proposal -> state becomes "rejected".
    approval.reject(invoice_proposal, session_state, audit_log)
    assert session_state["proposal_state"] == "rejected"

    with patch("paypal_service.create_and_send_invoice") as mock_create:
        result = approval.approve(invoice_proposal, session_state, audit_log)

    assert result["status"] == "duplicate_rejected"
    mock_create.assert_not_called()
    # Reject's state is preserved; PayPal was not re-invoked.
    assert session_state["proposal_state"] == "rejected"


def test_repeated_approve_blocked(invoice_proposal):
    """A second Approve after a completed approval is rejected as a duplicate."""
    session_state = {"proposal_state": "pending"}
    audit_log = []

    with patch("paypal_service.revalidate") as mock_revalidate, patch(
        "paypal_service.create_and_send_invoice"
    ) as mock_create:
        mock_revalidate.return_value = paypal_service.ValidationResult(ok=True)
        mock_create.return_value = {"status": "sent", "invoice_id": "INV2-TEST"}

        first = approval.approve(invoice_proposal, session_state, audit_log)
        assert first["status"] == "sent"
        assert session_state["proposal_state"] == "completed"

        second = approval.approve(invoice_proposal, session_state, audit_log)

    assert second["status"] == "duplicate_rejected"
    # PayPal was reached exactly once (only the first, successful Approve).
    assert mock_create.call_count == 1


# ---------------------------------------------------------------------------
# Reminder flow
# ---------------------------------------------------------------------------


def test_reminder_approval_success(reminder_proposal):
    """Approving a ReminderProposal sends a reminder and completes the state."""
    session_state = {"proposal_state": "pending"}
    audit_log = []

    with patch("paypal_service.revalidate") as mock_revalidate, patch(
        "paypal_service.send_reminder"
    ) as mock_remind:
        mock_revalidate.return_value = paypal_service.ValidationResult(ok=True)
        mock_remind.return_value = {"status": "sent"}

        result = approval.approve(reminder_proposal, session_state, audit_log)

    assert result["status"] == "sent"
    assert session_state["proposal_state"] == "completed"

    assert len(audit_log) == 2
    assert audit_log[0].action_type == "approved"
    assert audit_log[1].action_type == "executed"
    assert audit_log[0].proposal_id == reminder_proposal.proposal_id
    assert audit_log[1].proposal_id == reminder_proposal.proposal_id
    # The reminder was dispatched with the proposal's invoice id and note.
    mock_remind.assert_called_once_with(
        reminder_proposal.invoice_id, reminder_proposal.proposed_note
    )


# ---------------------------------------------------------------------------
# Audit-trail correlation
# ---------------------------------------------------------------------------


def test_audit_log_proposal_id_correlation(invoice_proposal):
    """Every audit entry produced for one proposal shares the same proposal_id."""
    session_state = {"proposal_state": "pending"}
    audit_log = []

    with patch("paypal_service.revalidate") as mock_revalidate, patch(
        "paypal_service.create_and_send_invoice"
    ) as mock_create:
        mock_revalidate.return_value = paypal_service.ValidationResult(ok=True)
        mock_create.return_value = {"status": "sent", "invoice_id": "INV2-TEST"}

        approval.approve(invoice_proposal, session_state, audit_log)

    assert len(audit_log) >= 2
    for entry in audit_log:
        assert entry.proposal_id == invoice_proposal.proposal_id
