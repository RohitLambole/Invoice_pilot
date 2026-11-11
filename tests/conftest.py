"""Shared fixtures and import-time dependency stubbing for the approval-engine
unit tests.

The tests exercise the approval state machine in isolation. They must never
reach the real PayPal API and must not depend on live credentials being
present in ``.env``. To guarantee this, the heavy/external dependencies are
stubbed *before* :mod:`approval` (or :mod:`paypal_service`) is imported:

- ``paypal_agent_toolkit.*`` is replaced with lightweight stubs so that
  ``PayPalToolkit(...).get_tools()`` performs no network or auth work at
  import time (and works even when the toolkit package is not installed).
- ``config`` is replaced with dummy credentials so :mod:`paypal_service` can
  be imported without a populated ``.env``.

The functions under test (``approval.approve`` / ``approval.reject``) and the
real ``paypal_service.ValidationResult`` remain untouched. Individual test
cases patch the PayPal *write* functions (``create_and_send_invoice``,
``send_reminder``) and ``revalidate`` where needed.
"""

import sys
import types
from decimal import Decimal


def _install_stubs() -> None:
    """Inject stub modules into ``sys.modules`` for hermetic testing.

    Idempotent: safe to call more than once.
    """

    # --- paypal_agent_toolkit (top-level package) -----------------------
    root = types.ModuleType("paypal_agent_toolkit")
    root.__path__ = []
    sys.modules["paypal_agent_toolkit"] = root

    # --- paypal_agent_toolkit.shared (subpackage) -----------------------
    shared = types.ModuleType("paypal_agent_toolkit.shared")
    shared.__path__ = []
    sys.modules["paypal_agent_toolkit.shared"] = shared
    root.shared = shared

    # --- paypal_agent_toolkit.shared.configuration ---------------------
    configuration = types.ModuleType("paypal_agent_toolkit.shared.configuration")

    class Configuration:
        def __init__(self, *args, **kwargs):
            pass

    class Context:
        def __init__(self, *args, **kwargs):
            pass

    configuration.Configuration = Configuration
    configuration.Context = Context
    sys.modules["paypal_agent_toolkit.shared.configuration"] = configuration
    shared.configuration = configuration

    # --- paypal_agent_toolkit.langchain (subpackage) -------------------
    langchain = types.ModuleType("paypal_agent_toolkit.langchain")
    langchain.__path__ = []
    sys.modules["paypal_agent_toolkit.langchain"] = langchain
    root.langchain = langchain

    # --- paypal_agent_toolkit.langchain.toolkit ------------------------
    toolkit = types.ModuleType("paypal_agent_toolkit.langchain.toolkit")

    class PayPalToolkit:
        def __init__(self, *args, **kwargs):
            pass

        def get_tools(self):
            # No real tools; write operations are mocked per-test.
            return []

    toolkit.PayPalToolkit = PayPalToolkit
    sys.modules["paypal_agent_toolkit.langchain.toolkit"] = toolkit
    langchain.toolkit = toolkit

    # --- config (dummy credentials) ------------------------------------
    config_stub = types.ModuleType("config")
    config_stub.PAYPAL_CLIENT_ID = "test-client-id"
    config_stub.PAYPAL_SECRET = "test-secret"
    config_stub.GOOGLE_API_KEY = "test-api-key"
    config_stub.AMOUNT_CAP = 1000.00
    config_stub.CURRENCY = "USD"
    config_stub.DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
    config_stub.GEMINI_MODEL = "gemini-2.5-flash"
    sys.modules["config"] = config_stub


# Install stubs at conftest import time — before any test module imports
# approval (which transitively imports paypal_service and config).
_install_stubs()

import pytest  # noqa: E402  (import after stubs are in place)

from models import InvoiceProposal, ReminderProposal  # noqa: E402


@pytest.fixture
def invoice_proposal() -> InvoiceProposal:
    """A valid ``InvoiceProposal`` for create-and-send flows."""
    return InvoiceProposal(
        client_name="Rahul",
        client_email="rahul@example.com",
        amount=Decimal("300.00"),
        description="Logo design",
    )


@pytest.fixture
def reminder_proposal() -> ReminderProposal:
    """A valid ``ReminderProposal`` for the reminder flow."""
    return ReminderProposal(
        invoice_id="INV2-TEST",
        client_name="Rahul",
        amount_due=Decimal("300.00"),
        proposed_note="Payment is overdue, please settle soon.",
    )
