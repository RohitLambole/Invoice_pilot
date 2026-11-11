"""Property-based test for the amount cap and currency invariant (Task 2.2).

**Validates: Requirements 2.1, 2.3, 2.6**

Property 1: Amount_Cap_and_Currency invariant
For ALL InvoiceProposals, the validated amount satisfies 0 < amount <= 1000.00
and currency == "USD". Invalid amounts (negative, zero, over cap) are rejected
at construction time by Pydantic; currency other than USD is rejected by the
field validator.

This tests ``models.py`` validation directly with no PayPal calls.
"""

from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from models import AMOUNT_CAP, CURRENCY, InvoiceProposal


def _make_proposal(amount: Decimal, currency: str | None = None) -> InvoiceProposal:
    """Helper: build an InvoiceProposal with an optional currency override."""
    kwargs = dict(
        client_name="Test",
        client_email="test@example.com",
        amount=amount,
        description="Test",
    )
    if currency is not None:
        kwargs["currency"] = currency
    return InvoiceProposal(**kwargs)


# ---------------------------------------------------------------------------
# Property-based test (Hypothesis)
# ---------------------------------------------------------------------------


@settings(deadline=None, max_examples=200)
@given(st.floats(allow_nan=False, allow_infinity=False))
def test_amount_cap_and_currency(amount):
    """For every float, constructing an InvoiceProposal either rejects it
    (ValidationError) or yields an amount strictly greater than 0 and at most
    the $1,000 cap, with currency == "USD".

    **Validates: Requirements 2.1, 2.3, 2.6**
    """
    try:
        proposal = _make_proposal(Decimal(str(amount)))
    except ValidationError:
        # Invalid amounts (<=0 or >cap) are correctly rejected — the
        # invariant holds because the bad value never becomes a proposal.
        return

    # If construction succeeded, the amount must satisfy the cap bounds.
    assert Decimal("0") < proposal.amount <= AMOUNT_CAP
    # Currency is always USD after construction.
    assert proposal.currency == CURRENCY


# ---------------------------------------------------------------------------
# Explicit edge-case tests (non-Hypothesis)
# ---------------------------------------------------------------------------


def test_amount_999_99_accepted():
    """999.99 is within the cap and must be accepted."""
    proposal = _make_proposal(Decimal("999.99"))
    assert proposal.amount == Decimal("999.99")
    assert proposal.currency == "USD"


def test_amount_1000_00_accepted():
    """The cap boundary 1000.00 is accepted (le is inclusive)."""
    proposal = _make_proposal(Decimal("1000.00"))
    assert proposal.amount == Decimal("1000.00")
    assert proposal.currency == "USD"


def test_amount_1000_01_rejected():
    """1000.01 exceeds the cap and must be rejected."""
    with pytest.raises(ValidationError):
        _make_proposal(Decimal("1000.01"))


def test_amount_zero_rejected():
    """Zero fails the gt=0 constraint and must be rejected."""
    with pytest.raises(ValidationError):
        _make_proposal(Decimal("0"))


def test_amount_negative_rejected():
    """A negative amount fails gt=0 and must be rejected."""
    with pytest.raises(ValidationError):
        _make_proposal(Decimal("-1"))


def test_non_usd_currency_rejected():
    """Currency other than USD is rejected by the field validator."""
    with pytest.raises(ValidationError):
        _make_proposal(Decimal("100"), currency="EUR")
