"""InvoicePilot Streamlit UI (``app.py``).

Single-page chat-based billing agent UI with three sections:

1. Chat interface (top) — talk to the agent, which can read invoices and
   *propose* new invoices or reminders.
2. Pending proposal approval card (middle) — shown only when a proposal exists.
   Every money-moving action is gated behind an explicit Approve/Reject click.
3. Audit log panel (bottom) — chronological trail of proposed/approved/
   rejected/executed/error events.

Security boundary
------------------
This module imports ``agent``, ``approval``, ``audit_log``, and ``models``.
It does NOT import ``paypal_service`` directly — all write operations go
through ``approval.approve()`` after the user clicks Approve. The agent is
imported lazily (inside the chat handler) so this module stays importable
and unit-testable without live credentials or a running Streamlit server.

Session state keys
------------------
- ``messages``            : list[dict] — chat history ``{"role", "content"}``
- ``pending_proposal``     : dict | None — raw proposal JSON from the agent tool
- ``pending_proposal_id``  : str | None — uuid4 generated when a proposal is parsed
- ``audit_log``            : list — of ``AuditLogEntry`` objects
- ``proposal_state``       : str — ``pending`` | ``executing`` | ``completed`` |
  ``error`` | ``timeout_ambiguous`` | ``rejected``
"""

import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional
from uuid import uuid4

import streamlit as st
from langchain_core.messages import AIMessage, ToolMessage

import approval
from audit_log import add_entry
from models import InvoiceProposal, ReminderProposal


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Tool names whose ``ToolMessage`` output carries a structured proposal.
PROPOSAL_TOOL_NAMES = ("propose_create_invoice", "propose_send_reminder")

#: Initial proposal state on first load.
INITIAL_PROPOSAL_STATE = "pending"


# ---------------------------------------------------------------------------
# Testable helper functions (no Streamlit / agent dependency)
# ---------------------------------------------------------------------------


def extract_proposal(result: dict) -> Optional[dict]:
    """Scan agent result messages (reverse order) for the latest proposal.

    Returns the parsed proposal dict when a proposal tool returned valid JSON
    without an ``"error"`` key, or ``None`` when no proposal is found.

    The scan goes in reverse so the *latest* proposal wins when the agent
    called a proposal tool more than once in a single turn.
    """
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, ToolMessage):
            if msg.name in PROPOSAL_TOOL_NAMES:
                try:
                    data = json.loads(msg.content)
                except (json.JSONDecodeError, TypeError):
                    continue
                if "error" not in data:
                    return data
    return None


def build_proposal(pending: dict, proposal_id: str):
    """Build a typed proposal object from the raw pending-proposal dict.

    Returns an :class:`InvoiceProposal` or :class:`ReminderProposal`, or
    ``None`` when the ``action_type`` is not recognised.
    """
    action_type = pending.get("action_type")
    if action_type == "create_invoice":
        return InvoiceProposal(
            proposal_id=proposal_id,
            client_name=pending["client_name"],
            client_email=pending["client_email"],
            amount=Decimal(pending["amount"]),
            currency=pending.get("currency", "USD"),
            description=pending["description"],
        )
    if action_type == "send_invoice_reminder":
        return ReminderProposal(
            proposal_id=proposal_id,
            invoice_id=pending["invoice_id"],
            client_name=pending["client_name"],
            amount_due=Decimal(pending["amount_due"]),
            proposed_note=pending.get("proposed_note") or None,
        )
    return None


def auto_reject_old_proposal(session_state: dict, audit_log: list) -> bool:
    """Auto-reject a still-pending proposal when a new chat message arrives.

    Design assumption (OQ-5): only one pending proposal at a time. If a new
    message arrives while ``proposal_state`` is ``"pending"`` and a proposal
    exists, the old proposal is rejected and logged before the new message is
    processed.

    Returns ``True`` if an old proposal was auto-rejected, ``False`` otherwise.
    """
    if (
        session_state.get("proposal_state") == "pending"
        and session_state.get("pending_proposal") is not None
    ):
        old = session_state["pending_proposal"]
        old_id = session_state.get("pending_proposal_id")
        # Build a lightweight proposal-like object — reject() only needs
        # ``action_type`` and ``proposal_id``.
        proxy = SimpleNamespace(
            action_type=old.get("action_type", "unknown"),
            proposal_id=old_id,
        )
        approval.reject(proxy, session_state, audit_log)
        # Clear the old pending proposal so the new one can take its place.
        session_state["pending_proposal"] = None
        session_state["pending_proposal_id"] = None
        return True
    return False


def handle_approve(session_state: dict, audit_log: list) -> dict:
    """Handle the Approve button click.

    Builds the typed proposal from the pending dict and delegates to
    :func:`approval.approve`. Returns the result dict from the approval
    engine (``sent``, ``error``, ``timeout_ambiguous``, ``duplicate_rejected``).
    """
    pending = session_state.get("pending_proposal")
    proposal_id = session_state.get("pending_proposal_id")
    if pending is None or proposal_id is None:
        return {"status": "error", "error": "No pending proposal to approve."}
    try:
        proposal = build_proposal(pending, proposal_id)
    except Exception as exc:  # noqa: BLE001 — never crash the UI
        return {"status": "error", "error": f"Invalid proposal data: {exc}"}
    if proposal is None:
        return {
            "status": "error",
            "error": f"Unknown proposal type: {pending.get('action_type')}",
        }
    result = approval.approve(proposal, session_state, audit_log)
    # Log duplicate rejections to the audit log so there is a visible trail
    # even when the approve button is blocked by the state guard.
    if result.get("status") == "duplicate_rejected":
        add_entry(
            audit_log,
            "duplicate_rejected",
            f"Duplicate approval rejected: {result.get('error', '')}",
            proposal_id=proposal_id,
        )
    return result


def handle_reject(session_state: dict, audit_log: list) -> dict:
    """Handle the Reject button click.

    Builds the typed proposal, delegates to :func:`approval.reject`, and
    clears the pending proposal. Returns the result dict (``rejected``).
    """
    pending = session_state.get("pending_proposal")
    proposal_id = session_state.get("pending_proposal_id")
    if pending is None or proposal_id is None:
        return {"status": "error", "error": "No pending proposal to reject."}
    try:
        proposal = build_proposal(pending, proposal_id)
    except Exception:  # noqa: BLE001 — fall back to a lightweight proxy
        proposal = SimpleNamespace(
            action_type=pending.get("action_type", "unknown"),
            proposal_id=proposal_id,
        )
    if proposal is None:
        proposal = SimpleNamespace(
            action_type=pending.get("action_type", "unknown"),
            proposal_id=proposal_id,
        )
    result = approval.reject(proposal, session_state, audit_log)
    # Clear the pending proposal so the card disappears.
    session_state["pending_proposal"] = None
    session_state["pending_proposal_id"] = None
    return result

def handle_dismiss(session_state: dict) -> None:
    """Dismiss the proposal card WITHOUT rejecting the proposal.

    Used for timeout_ambiguous proposals: the card is removed from
    the UI but the state remains timeout_ambiguous so the approval
    guard continues blocking any re-execution. This is distinct from
    Reject, which explicitly rejects the proposal and sets state to
    "rejected".
    """
    session_state["pending_proposal"] = None
    session_state["pending_proposal_id"] = None
    # Do NOT change proposal_state - it stays as timeout_ambiguous.


def _extract_ai_content(messages: list) -> str:
    """Extract the assistant's final text response from agent result messages."""
    ai_msgs = [m for m in messages if isinstance(m, AIMessage)]
    if not ai_msgs:
        return "I couldn't process that request."
    content = ai_msgs[-1].content
    # Handle content as a list of blocks (some LangChain versions).
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "".join(parts) or "I couldn't process that request."
    return content or "I couldn't process that request."


# ---------------------------------------------------------------------------
# Streamlit rendering (not unit-tested — requires a browser)
# ---------------------------------------------------------------------------


def init_session_state() -> None:
    """Initialize session-state keys on first load."""
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "pending_proposal" not in st.session_state:
        st.session_state["pending_proposal"] = None
    if "pending_proposal_id" not in st.session_state:
        st.session_state["pending_proposal_id"] = None
    if "audit_log" not in st.session_state:
        st.session_state["audit_log"] = []
    if "proposal_state" not in st.session_state:
        st.session_state["proposal_state"] = INITIAL_PROPOSAL_STATE


def render_chat() -> None:
    """Render the chat interface and handle user input.

    On user message: append the user message, invoke the agent, display the
    assistant response, and scan for proposals. A pending proposal is only
    auto-rejected when a NEW proposal is extracted from the agent's response
    (OQ-5); a clarification message (no new proposal) leaves the pending
    proposal intact.
    """
    # Display existing chat history.
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle new user input.
    if prompt := st.chat_input("Ask InvoicePilot to create an invoice or check invoices…"):
        # Append and display the user message.
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Invoke the agent (lazy import — avoid constructing at module load).
        try:
            from agent import agent as agent_graph

            result = agent_graph.invoke({"messages": st.session_state["messages"]})
        except Exception as exc:  # noqa: BLE001 — never crash the UI
            st.error(
                f"⚠️ Unable to reach the AI service. Please try again in a "
                f"moment. (Error: {type(exc).__name__})"
            )
            return

        # Extract and display the assistant's final response.
        assistant_content = _extract_ai_content(result.get("messages", []))
        st.session_state["messages"].append(
            {"role": "assistant", "content": assistant_content}
        )
        with st.chat_message("assistant"):
            st.markdown(assistant_content)

        # Scan for a proposal from the agent's tool calls.
        proposal = extract_proposal(result)
        if proposal is not None:
            # A new proposal was extracted. If there is an existing pending
            # proposal, auto-reject it before storing the new one (OQ-5:
            # only one pending proposal at a time). A clarification message
            # (no new proposal) leaves the pending proposal intact.
            auto_reject_old_proposal(st.session_state, st.session_state["audit_log"])
            proposal_id = str(uuid4())
            st.session_state["pending_proposal"] = proposal
            st.session_state["pending_proposal_id"] = proposal_id
            st.session_state["proposal_state"] = "pending"
            add_entry(
                st.session_state["audit_log"],
                "proposed",
                f"Proposed: {proposal.get('action_type', 'unknown')}",
                proposal_id=proposal_id,
            )


def _render_proposal_details(pending: dict) -> None:
    """Render the proposal-specific fields inside the approval card."""
    action_type = pending.get("action_type")
    if action_type == "create_invoice":
        st.write(f"**Client:** {pending.get('client_name', '')}")
        st.write(f"**Email:** {pending.get('client_email', '')}")
        st.write(
            f"**Amount:** ${pending.get('amount', '')} "
            f"{pending.get('currency', 'USD')}"
        )
        st.write(f"**Description:** {pending.get('description', '')}")
    elif action_type == "send_invoice_reminder":
        st.write(f"**Invoice ID:** {pending.get('invoice_id', '')}")
        st.write(f"**Client:** {pending.get('client_name', '')}")
        st.write(f"**Amount Due:** ${pending.get('amount_due', '')}")
        note = pending.get("proposed_note", "")
        if note:
            st.write(f"**Proposed Note:** {note}")


def _set_result_msg(result: dict) -> None:
    """Store the approve/reject result as a displayable message in session state."""
    status = result.get("status")
    if status == "sent":
        st.session_state["_result_msg"] = (
            "success",
            f"✅ Invoice created and sent! Invoice ID: "
            f"{result.get('invoice_id', 'unknown')}",
        )
    elif status == "error":
        st.session_state["_result_msg"] = (
            "error",
            f"❌ Error: {result.get('error', 'Unknown error')}",
        )
    elif status in ("timeout_ambiguous", "malformed_response"):
        st.session_state["_result_msg"] = (
            "warning",
            "The request timed out or returned an unexpected response. "
            "The invoice may or may not have been created. DO NOT retry. "
            "Check your PayPal sandbox dashboard to verify before taking "
            "any further action.",
        )
    elif status == "duplicate_rejected":
        st.session_state["_result_msg"] = (
            "info",
            "This proposal was already processed.",
        )
    elif status == "rejected":
        st.session_state["_result_msg"] = ("info", "Proposal rejected.")


def _display_result_msg(msg: tuple) -> None:
    """Display a stored result message tuple (type, text)."""
    msg_type, msg_text = msg
    if msg_type == "success":
        st.success(msg_text)
    elif msg_type == "error":
        st.error(msg_text)
    elif msg_type == "warning":
        st.warning(msg_text)
    elif msg_type == "info":
        st.info(msg_text)


# LIMITATION: Only one active proposal can be displayed at a time (OQ-5 design
# assumption). Multiple pending proposals are not supported in the P0 MVP.
# P1 batch reminders will require extending to a pending_proposals list.

def render_proposal_card() -> None:
    """Render the pending proposal approval card.

    The card is only shown when ``pending_proposal`` is not ``None`` and
    ``proposal_state`` is not ``"rejected"``.
    """
    pending = st.session_state.get("pending_proposal")
    state = st.session_state.get("proposal_state", "pending")

    # Display any pending result message from a previous approve/reject.
    result_msg = st.session_state.pop("_result_msg", None)
    if result_msg:
        _display_result_msg(result_msg)

    # Don't show the card when there's no proposal or it was rejected.
    if pending is None or state == "rejected":
        return

    proposal_id = st.session_state.get("pending_proposal_id", "")

    with st.container(border=True):
        st.markdown(
            "⚠️ **PROPOSED — Not yet created. Review and approve to execute.**"
        )
        _render_proposal_details(pending)

        if state == "pending":
            col1, col2 = st.columns(2)
            with col1:
                if st.button(
                    "✅ Approve",
                    key=f"approve_{proposal_id}",
                    type="primary",
                ):
                    result = handle_approve(
                        st.session_state, st.session_state["audit_log"]
                    )
                    _set_result_msg(result)
                    st.rerun()
            with col2:
                if st.button("❌ Reject", key=f"reject_{proposal_id}"):
                    result = handle_reject(
                        st.session_state, st.session_state["audit_log"]
                    )
                    _set_result_msg(result)
                    st.rerun()
        elif state == "executing":
            st.info("⏳ Executing…")
        elif state == "completed":
            st.success("✅ Completed")
        elif state == "error":
            st.error(
                "❌ Execution failed. Send a new message to create a new "
                "proposal."
            )
        elif state == "timeout_ambiguous":
            st.warning(
                "The request timed out or returned an unexpected response. "
                "The invoice may or may not have been created. DO NOT retry. "
                "Check your PayPal sandbox dashboard to verify before taking "
                "any further action."
            )
            if st.button("Dismiss", key=f"dismiss_{proposal_id}"):
                handle_dismiss(st.session_state)
                st.rerun()


def render_audit_log() -> None:
    """Render the audit log panel in reverse chronological order (newest first)."""
    with st.expander("📋 Audit Log", expanded=False):
        audit_log = st.session_state.get("audit_log", [])
        if not audit_log:
            st.info("No audit events yet.")
            return
        for entry in reversed(audit_log):
            ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
            line = f"**{ts}** | `{entry.action_type}` | {entry.description}"
            if entry.result:
                line += f" — {entry.result}"
            if entry.proposal_id:
                line += f"  `(id: {entry.proposal_id[:8]}…)`"
            st.markdown(line)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Render the full InvoicePilot UI."""
    st.set_page_config(
        page_title="InvoicePilot",
        page_icon="🧾",
        layout="centered",
    )
    st.title("🧾 InvoicePilot")
    st.caption(
        "Chat-based billing assistant with human-in-the-loop approval. "
        "The agent can read invoices and *propose* actions — you approve "
        "every money-moving step."
    )

    init_session_state()
    render_chat()
    render_proposal_card()
    render_audit_log()


if __name__ == "__main__":
    main()
