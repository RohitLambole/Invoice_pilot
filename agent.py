"""InvoicePilot LangChain agent (``agent.py``).

Builds the LangChain agent with :func:`create_agent` and registers a strict
tool whitelist: read-only PayPal tools (``list_invoices``, ``get_invoice``)
plus custom proposal tools that only validate inputs and return structured
JSON. The agent can read invoices and *propose* new invoices or reminders,
but it can NEVER execute a money-moving or destructive PayPal operation
directly -- those are gated behind the application-layer approval engine.

Security boundary:
- This module never depends on ``paypal_service`` or ``approval``. Those
  modules hold the gated write tools and the approval state machine; the
  agent must never hold a write or destructive tool.
- The PayPal toolkit configured below is read-only: only the ``list`` and
  ``get`` invoice actions are enabled. No create/send/reminder/cancel/
  refund/payment tool is ever registered with the agent.
- The custom proposal tools (``lookup_client_email``,
  ``propose_create_invoice``, ``propose_send_reminder``) validate inputs and
  return structured JSON proposals; they never call PayPal.

The tool whitelist is the primary mitigation for prompt injection: even if a
malicious description tricks the agent, it has no write tool to escalate to.
"""

from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from paypal_agent_toolkit.langchain.toolkit import PayPalToolkit
from paypal_agent_toolkit.shared.configuration import Configuration, Context

from config import GEMINI_MODEL, GOOGLE_API_KEY, PAYPAL_CLIENT_ID, PAYPAL_SECRET
from tools import lookup_client_email, propose_create_invoice, propose_send_reminder


# ---------------------------------------------------------------------------
# Read-only PayPal toolkit
# ---------------------------------------------------------------------------

# Only the ``list`` and ``get`` invoice actions are enabled, so the toolkit
# exposes ONLY list_invoices and get_invoice. No create/send/reminder/cancel/
# refund/payment action is enabled -- those live in paypal_service.py and are
# only reachable after the Freelancer clicks Approve.
read_configuration = Configuration(
    actions={"invoices": {"list": True, "get": True}},
    context=Context(sandbox=True),
)

paypal_toolkit = PayPalToolkit(
    client_id=PAYPAL_CLIENT_ID,
    secret=PAYPAL_SECRET,
    configuration=read_configuration,
)

# Read-only tools returned by the toolkit: list_invoices and get_invoice.
read_tools = paypal_toolkit.get_tools()

# ---------------------------------------------------------------------------
# Custom proposal tools (read-only / proposal-only; never execute PayPal)
# ---------------------------------------------------------------------------

proposal_tools = [lookup_client_email, propose_create_invoice, propose_send_reminder]

# Every tool the agent may call: read-only PayPal tools + proposal tools.
all_tools = read_tools + proposal_tools

# ---------------------------------------------------------------------------
# System prompt (PRD section 9, with the human-in-the-loop clarifications)
# ---------------------------------------------------------------------------

system_prompt = """You are InvoicePilot, a billing assistant for a freelancer. You can read
invoices and propose new invoices or reminders. You never create, send or
remind directly: always return a proposal and wait for the user to approve
it. Use USD only. Never propose an invoice over $1,000. If the client's
email is not known, ask for it before proposing. Never invent amounts,
clients or invoice numbers. When summarising invoices, report only what
the tools returned. If a request is outside invoicing (refunds, deleting,
cancelling), say you can't do that here.

IMPORTANT: You cannot execute billing operations. You can only propose
them. You must never claim an invoice was created or sent until the
application confirms the result after user approval. If information is
missing (client name, amount, description, or email), ask the user for it
before proposing."""

# ---------------------------------------------------------------------------
# Agent construction
# ---------------------------------------------------------------------------

model = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=GOOGLE_API_KEY)

agent = create_agent(
    model=model,
    tools=all_tools,
    system_prompt=system_prompt,
)

# ---------------------------------------------------------------------------
# Tool-whitelist metadata (drives the security-boundary / whitelist tests)
# ---------------------------------------------------------------------------

# The only PayPal tools the agent is allowed to hold (read-only).
EXPECTED_READ_TOOL_NAMES = ["list_invoices", "get_invoice"]

# The custom proposal tools the agent is allowed to hold.
EXPECTED_PROPOSAL_TOOL_NAMES = [
    "lookup_client_email",
    "propose_create_invoice",
    "propose_send_reminder",
]

# PayPal tools that MUST NEVER be exposed to the agent. These are the
# write/destructive tools gated behind the approval engine. If any of these
# names ever appears in ``all_tools``, the security boundary is broken.
NEVER_EXPOSED_TOOL_NAMES = [
    "create_invoice",
    "send_invoice",
    "send_invoice_reminder",
    "cancel_sent_invoice",
    "generate_invoice_qr_code",
    "record_refund_for_invoice",
    "record_payment_for_invoice",
]


__all__ = [
    "agent",
    "all_tools",
    "read_tools",
    "proposal_tools",
    "paypal_toolkit",
    "system_prompt",
    "EXPECTED_READ_TOOL_NAMES",
    "EXPECTED_PROPOSAL_TOOL_NAMES",
    "NEVER_EXPOSED_TOOL_NAMES",
]
