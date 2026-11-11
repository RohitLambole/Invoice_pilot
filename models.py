"""Pydantic data models for InvoicePilot.

Defines the structured proposal, audit log, and client record models used
across the application. All monetary fields use :class:`decimal.Decimal` for
exact arithmetic -- never ``float`` (Requirement 2). The amount cap and
USD-only currency rules are enforced here as the primary validation layer.

This module deliberately does NOT import :mod:`config`: ``config`` fails fast
when ``.env`` secrets are missing, and the data models must remain importable
(and unit-testable) without any credentials present. The amount cap is
therefore defined locally and mirrors ``config.AMOUNT_CAP``.
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

#: Maximum invoice amount in USD (Requirement 2.1). Kept local so this module
#: stays importable without loading .env secrets; mirrors config.AMOUNT_CAP.
AMOUNT_CAP = Decimal("1000.00")

#: The only supported currency (Requirement 2.3).
CURRENCY = "USD"

# Simplified RFC 5322 email pattern: ``local@domain.tld`` with no whitespace
# or additional ``@`` symbols.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvoiceProposal(BaseModel):
    """Structured proposal for creating and sending a PayPal invoice.

    Produced by the agent's ``propose_create_invoice`` tool and rendered as an
    Approval_Card. The agent never executes the invoice; the application only
    calls ``create_invoice`` after the Freelancer clicks Approve.
    """

    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: Literal["create_invoice"] = "create_invoice"
    client_name: str = Field(min_length=1)
    client_email: str = Field(min_length=3)
    amount: Decimal = Field(gt=0, le=AMOUNT_CAP)
    currency: str = Field(default=CURRENCY)
    description: str = Field(min_length=1)

    @field_validator("client_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate a simplified RFC 5322 email and normalise to lower case."""
        if not _EMAIL_RE.match(v):
            raise ValueError(f"Invalid email format: {v}")
        return v.lower().strip()

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Enforce USD as the only supported currency."""
        if v != CURRENCY:
            raise ValueError(f"Currency must be USD, got {v}")
        return v


class ReminderProposal(BaseModel):
    """Structured proposal for sending a payment reminder for an overdue invoice.

    ``proposed_note`` is the text the Freelancer SEES on the approval card. It
    is passed to ``send_invoice_reminder`` as the optional ``note`` parameter
    (spike-confirmed supported).
    """

    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: Literal["send_invoice_reminder"] = "send_invoice_reminder"
    invoice_id: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    amount_due: Decimal = Field(gt=0)
    proposed_note: Optional[str] = None


class AuditLogEntry(BaseModel):
    """A single audit log entry recording a proposed, approved, rejected,
    executed, or error event.

    All events for the same proposal share the same ``proposal_id``, enabling
    full audit trail correlation.

    Note: audit history exists in session state only -- not durable across
    page refreshes (OQ-6 design assumption; PRD: no database).
    """

    timestamp: datetime
    proposal_id: Optional[str] = None
    action_type: Literal["proposed", "approved", "rejected", "executed", "error", "duplicate_rejected"]
    description: str
    result: Optional[str] = None


class ClientRecord(BaseModel):
    """A single client entry mapping a name to an email address."""

    name: str
    email: str


__all__ = [
    "AMOUNT_CAP",
    "CURRENCY",
    "InvoiceProposal",
    "ReminderProposal",
    "AuditLogEntry",
    "ClientRecord",
]
