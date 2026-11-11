"""Unit tests for the InvoicePilot agent (``agent.py``).

These tests verify the agent's tool whitelist and security boundary without
contacting PayPal or Gemini. The ``conftest.py`` stubs ``paypal_agent_toolkit``
(so ``PayPalToolkit.get_tools()`` returns ``[]``) and ``config`` (with dummy
credentials) so that importing :mod:`agent` is hermetic: no network call is
made and no live credentials are required.

What is verified:
- ``agent.py`` does not depend on the gated write modules
  (``paypal_service`` / ``approval``).
- The tool-whitelist metadata (``EXPECTED_READ_TOOL_NAMES``,
  ``EXPECTED_PROPOSAL_TOOL_NAMES``, ``NEVER_EXPOSED_TOOL_NAMES``) is defined
  with the right names.
- No ``NEVER_EXPOSED`` tool name appears in the agent's ``all_tools``.
- The proposal tools return structured JSON proposals, never PayPal results.
"""

import inspect
import json

import agent


# ---------------------------------------------------------------------------
# Level 1: static import / export checks (no PayPal needed)
# ---------------------------------------------------------------------------


def test_agent_module_imports():
    """The agent module imports and exposes its public surface."""
    assert hasattr(agent, "agent")
    assert hasattr(agent, "all_tools")
    assert hasattr(agent, "system_prompt")


def test_agent_is_constructed():
    """``create_agent`` produced a runnable compiled graph."""
    # create_agent returns a CompiledStateGraph with invoke/stream methods.
    assert hasattr(agent.agent, "invoke")
    assert hasattr(agent.agent, "stream")


def test_whitelist_metadata_defined():
    """The tool-whitelist metadata lists are defined with the right names."""
    assert hasattr(agent, "EXPECTED_READ_TOOL_NAMES")
    assert hasattr(agent, "EXPECTED_PROPOSAL_TOOL_NAMES")
    assert hasattr(agent, "NEVER_EXPOSED_TOOL_NAMES")

    # Read-only PayPal tools.
    assert "list_invoices" in agent.EXPECTED_READ_TOOL_NAMES
    assert "get_invoice" in agent.EXPECTED_READ_TOOL_NAMES

    # Custom proposal tools.
    assert "lookup_client_email" in agent.EXPECTED_PROPOSAL_TOOL_NAMES
    assert "propose_create_invoice" in agent.EXPECTED_PROPOSAL_TOOL_NAMES
    assert "propose_send_reminder" in agent.EXPECTED_PROPOSAL_TOOL_NAMES


def test_never_exposed_disjoint_from_expected():
    """No never-exposed tool is also listed as expected/allowed."""
    allowed = set(agent.EXPECTED_READ_TOOL_NAMES) | set(
        agent.EXPECTED_PROPOSAL_TOOL_NAMES
    )
    for name in agent.NEVER_EXPOSED_TOOL_NAMES:
        assert name not in allowed, f"'{name}' is both NEVER_EXPOSED and allowed"


def test_never_exposed_contains_required_names():
    """The never-exposed list covers all the destructive/write tool names."""
    required_never = {
        "create_invoice",
        "send_invoice",
        "send_invoice_reminder",
        "cancel_sent_invoice",
        "generate_invoice_qr_code",
        "record_refund_for_invoice",
        "record_payment_for_invoice",
    }
    assert required_never <= set(agent.NEVER_EXPOSED_TOOL_NAMES)


# ---------------------------------------------------------------------------
# Security boundary: agent.py must not depend on the write modules
# ---------------------------------------------------------------------------


def test_agent_does_not_import_write_modules():
    """agent.py source never references the gated write modules."""
    source = inspect.getsource(agent)
    assert "import paypal_service" not in source
    assert "import approval" not in source
    assert "from paypal_service" not in source
    assert "from approval" not in source


# ---------------------------------------------------------------------------
# Level 2: tool whitelist conformance (with stubs)
# ---------------------------------------------------------------------------


def test_tool_whitelist_conformance():
    """The agent's tool list contains only expected tools and no write tools."""
    all_tool_names = [t.name for t in agent.all_tools]

    # No never-exposed tool is registered with the agent.
    for name in agent.NEVER_EXPOSED_TOOL_NAMES:
        assert name not in all_tool_names, (
            f"NEVER_EXPOSED tool '{name}' found in agent tools: {all_tool_names}"
        )

    # The custom proposal tools are always registered.
    for name in agent.EXPECTED_PROPOSAL_TOOL_NAMES:
        assert name in all_tool_names, (
            f"Proposal tool '{name}' missing from agent tools: {all_tool_names}"
        )


def test_all_tools_only_contains_expected_names():
    """Every registered tool name is in the allowed whitelist."""
    allowed = set(agent.EXPECTED_READ_TOOL_NAMES) | set(
        agent.EXPECTED_PROPOSAL_TOOL_NAMES
    )
    all_tool_names = [t.name for t in agent.all_tools]
    for name in all_tool_names:
        assert name in allowed, (
            f"Unexpected tool '{name}' registered with the agent (not in {allowed})"
        )


# ---------------------------------------------------------------------------
# Proposal tools return JSON, never a PayPal result
# ---------------------------------------------------------------------------


def test_propose_create_invoice_returns_json_not_paypal():
    """propose_create_invoice returns a JSON proposal, not a PayPal call result."""
    from tools import propose_create_invoice

    result = propose_create_invoice.invoke(
        {
            "client_name": "Rahul",
            "client_email": "rahul@example.com",
            "amount": 300.0,
            "description": "Logo design",
        }
    )
    data = json.loads(result)
    assert data["action_type"] == "create_invoice"
    assert data["client_name"] == "Rahul"
    assert data["client_email"] == "rahul@example.com"
    assert data["amount"] == "300.00"
    assert data["currency"] == "USD"
    assert data["description"] == "Logo design"
    # It did NOT call PayPal: no PayPal response fields are present.
    assert "createResult" not in data
    assert "invoice_id" not in data


def test_propose_send_reminder_returns_json_not_paypal():
    """propose_send_reminder returns a JSON proposal, not a PayPal call result."""
    from tools import propose_send_reminder

    result = propose_send_reminder.invoke(
        {
            "invoice_id": "INV2-TEST",
            "client_name": "Rahul",
            "amount_due": 300.0,
        }
    )
    data = json.loads(result)
    assert data["action_type"] == "send_invoice_reminder"
    assert data["invoice_id"] == "INV2-TEST"
    assert data["client_name"] == "Rahul"
    assert data["amount_due"] == "300.00"
    # It did NOT call PayPal: no PayPal response fields are present.
    assert "createResult" not in data


def test_propose_create_invoice_blocks_over_cap():
    """propose_create_invoice refuses an amount over the $1,000 cap."""
    from tools import propose_create_invoice

    result = propose_create_invoice.invoke(
        {
            "client_name": "Rahul",
            "client_email": "rahul@example.com",
            "amount": 5000.0,
            "description": "Should be blocked",
        }
    )
    data = json.loads(result)
    assert "error" in data
    assert "createResult" not in data
