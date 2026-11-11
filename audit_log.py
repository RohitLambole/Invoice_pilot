"""Audit log service for InvoicePilot.

Records proposed, approved, rejected, executed, and error events into an
in-memory audit log held in Streamlit session state (OQ-6 design assumption;
PRD: no database).

The audit log is a plain Python ``list`` passed in by the caller. It is NOT
durable across page refreshes or server restarts -- this is by design.

The public interface is the :func:`add_entry` function (not a class method),
matching the design's session-state-based approach.
"""

from datetime import datetime, timezone

from models import AuditLogEntry


def add_entry(
    audit_log: list,
    action_type: str,
    description: str,
    result: str | None = None,
    proposal_id: str | None = None,
) -> None:
    """Append an entry to the audit log.

    Args:
        audit_log: The session-state list to append to (a plain ``list``).
        action_type: One of ``"proposed"``, ``"approved"``, ``"rejected"``,
            ``"executed"``, ``"error"``.
        description: Human-readable description of the event.
        result: Optional success message or error text.
        proposal_id: Optional proposal id correlating all events for the same
            proposal. Pass it for every call after the proposal is created so
            the full audit trail for a single action is linkable.

    The audit log lives in session state only. It is NOT durable across
    Streamlit page refreshes or server restarts. This is by design (PRD: no
    database).
    """
    entry = AuditLogEntry(
        timestamp=datetime.now(timezone.utc),
        proposal_id=proposal_id,
        action_type=action_type,
        description=description,
        result=result,
    )
    audit_log.append(entry)


__all__ = ["add_entry"]
