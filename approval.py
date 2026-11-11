"""Approval engine for InvoicePilot.

Manages the approval state machine, revalidates proposals before execution,
and orchestrates the create-and-send flow with partial failure handling.

The approval engine is the single gateway between a user's Approve/Reject
click and the PayPal write service. The agent never calls these functions —
only the Streamlit UI does, after the user clicks Approve or Reject.

State machine::

    PENDING -> EXECUTING -> COMPLETED | TIMEOUT_AMBIGUOUS | ERROR
    PENDING -> REJECTED
    EXECUTING -> (duplicate Approve rejected immediately)

Failure modes:
    A. Definite pre-execution failure (revalidation, auth error before any
       PayPal write) -> proposal_state = "error". Re-enable buttons; safe to
       retry.
    B. Malformed/unexpected response after a PayPal write was attempted
       -> proposal_state = "timeout_ambiguous". Non-retryable: a second
       Approve could create a duplicate invoice.
    C. Network timeout (ambiguous outcome) -> proposal_state =
       "timeout_ambiguous". Non-retryable.
"""

import paypal_service
from audit_log import add_entry


def approve(proposal, session_state, audit_log) -> dict:
    """Execute the approved proposal through the PayPal service.

    Guards:
    - Duplicate rejection: if ``proposal_state`` is in any terminal or in-flight
      state (executing, completed, timeout_ambiguous, rejected), the call is
      rejected immediately without touching PayPal.
    - In-progress lock: ``proposal_state`` is set to ``"executing"`` before any
      PayPal call, so a second Approve click (double-click race) is blocked.

    Args:
        proposal: An ``InvoiceProposal`` or ``ReminderProposal``.
        session_state: The Streamlit session-state dict (mutable). Must support
            ``.get("proposal_state", "pending")`` and item assignment.
        audit_log: The session-state audit log list.

    Returns:
        The result dict from ``paypal_service`` (or a guard/error dict).
    """
    # ------------------------------------------------------------------
    # 1. Duplicate / in-progress guard
    # ------------------------------------------------------------------
    current_state = session_state.get("proposal_state", "pending")
    # Block re-execution for all terminal or in-flight states.
    # timeout_ambiguous is explicitly blocked: the PayPal outcome is unknown
    # and a second Approve could create a duplicate invoice.
    # rejected is blocked: a Reject dismisses the proposal permanently; any
    # new action requires a fresh proposal from a new chat request.
    if current_state in ("executing", "completed", "timeout_ambiguous", "rejected"):
        return {
            "status": "duplicate_rejected",
            "error": f"Cannot approve: proposal is in state '{current_state}'.",
        }

    # ------------------------------------------------------------------
    # 2. Set in-progress flag BEFORE any PayPal call
    # ------------------------------------------------------------------
    session_state["proposal_state"] = "executing"

    # ------------------------------------------------------------------
    # 3. Revalidate before execution (defense in depth)
    # ------------------------------------------------------------------
    validated = paypal_service.revalidate(proposal)
    if not validated.ok:
        session_state["proposal_state"] = "error"
        add_entry(
            audit_log,
            "error",
            f"Revalidation failed: {validated.error}",
            proposal_id=proposal.proposal_id,
        )
        return {"status": "error", "error": validated.error}

    # ------------------------------------------------------------------
    # 4. Log the approval
    # ------------------------------------------------------------------
    add_entry(
        audit_log,
        "approved",
        f"Approved: {proposal.action_type}",
        proposal_id=proposal.proposal_id,
    )

    # ------------------------------------------------------------------
    # 5. Dispatch to PayPal service
    # ------------------------------------------------------------------
    if proposal.action_type == "create_invoice":
        result = paypal_service.create_and_send_invoice(proposal)
    elif proposal.action_type == "send_invoice_reminder":
        result = paypal_service.send_reminder(
            proposal.invoice_id, proposal.proposed_note
        )
    else:
        session_state["proposal_state"] = "error"
        add_entry(
            audit_log,
            "error",
            f"Unknown action type: {proposal.action_type}",
            proposal_id=proposal.proposal_id,
        )
        return {"status": "error", "error": f"Unknown action type: {proposal.action_type}"}

    # ------------------------------------------------------------------
    # 6. Handle results
    # ------------------------------------------------------------------
    if result["status"] == "sent":
        session_state["proposal_state"] = "completed"
        add_entry(
            audit_log,
            "executed",
            f"Executed: {proposal.action_type}",
            result=f"Invoice {result.get('invoice_id', '')} - sent",
            proposal_id=proposal.proposal_id,
        )
    elif result["status"] == "timeout_ambiguous":
        # Network timeout — PayPal write was attempted, outcome unknown.
        # Non-retryable: a second Approve could create a duplicate invoice.
        session_state["proposal_state"] = "timeout_ambiguous"
        add_entry(
            audit_log,
            "error",
            f"Timeout: outcome unknown for {proposal.action_type}",
            result=(
                "Check PayPal sandbox dashboard. Reject only dismisses the "
                "card; it does not resolve the PayPal transaction."
            ),
            proposal_id=proposal.proposal_id,
        )
    elif result["status"] == "malformed_response":
        # PayPal write was attempted but the response could not be parsed.
        # The invoice may or may not have been created and sent.
        # Non-retryable: a second Approve could create a duplicate invoice.
        session_state["proposal_state"] = "timeout_ambiguous"
        add_entry(
            audit_log,
            "error",
            f"Malformed response from PayPal for {proposal.action_type}",
            result=(
                "Outcome unknown — check PayPal sandbox dashboard. Reject "
                "only dismisses; it does not resolve the transaction."
            ),
            proposal_id=proposal.proposal_id,
        )
    else:
        # "error" — definite pre-execution failure (auth, validation,
        # revalidation). No PayPal write was attempted. Safe to re-enable
        # buttons for retry.
        session_state["proposal_state"] = "error"
        add_entry(
            audit_log,
            "error",
            f"Execution failed: {proposal.action_type}",
            result=result.get("error"),
            proposal_id=proposal.proposal_id,
        )

    # ------------------------------------------------------------------
    # 7. Return result
    # ------------------------------------------------------------------
    return result


def reject(proposal, session_state, audit_log) -> dict:
    """Dismiss the proposal and log the rejection.

    Always sets ``proposal_state`` to ``"rejected"`` regardless of the prior
    state. This prevents a ``timeout_ambiguous`` proposal from being silently
    retried: after Reject, the guard in :func:`approve` will block any further
    Approve click.

    For ``timeout_ambiguous`` proposals, Reject only dismisses the UI card.
    It does NOT establish whether PayPal created or sent the invoice. The
    user must verify the PayPal sandbox dashboard independently. Any
    subsequent billing action must use a fresh proposal from a new chat
    request.
    """
    session_state["proposal_state"] = "rejected"
    add_entry(
        audit_log,
        "rejected",
        f"Rejected: {proposal.action_type}",
        proposal_id=proposal.proposal_id,
    )
    return {"status": "rejected"}


__all__ = ["approve", "reject"]
