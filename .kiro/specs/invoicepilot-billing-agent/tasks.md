# Implementation Plan: InvoicePilot Billing Agent

## Overview

InvoicePilot is a chat-based billing agent for freelancers, built with Python, Streamlit, LangChain's `create_agent` with `ChatGoogleGenerativeAI` (Gemini), and the PayPal Agent Toolkit against the sandbox. The defining principle is human-in-the-loop approval: the agent layer can only read invoices and produce structured proposals; every money-moving action (create, send, remind) is executed by application code only after the Freelancer clicks Approve.

This plan translates the design into incremental, code-only tasks organized by priority (P0 first, then P1, then P2). Each task builds on prior steps and ends with the UI wiring everything together. The four P0 correctness properties from the design are covered by property-based tests (Hypothesis); unit tests cover validation and lookup logic. No task requires running the live app for acceptance — external behavior is verified via mocked tests, with optional integration tests gated behind sandbox credentials.

## Tasks

- [x] 0. PayPal and Gemini integration spike (P0 - prerequisite for tasks 6.1 and 7.1)
  - [x] 0.1 Package and API inspection (COMPLETED — see spike_results.md)
    - Installed paypal-agent-toolkit==1.1.0; confirmed tool names from get_tools(): list_invoices, get_invoice, create_invoice, send_invoice, send_invoice_reminder
    - Confirmed Python config keys: "list", "get", "create", "send", "sendReminder" all verified working
    - Confirmed create_invoice auto-sends (no separate send_invoice needed)
    - Confirmed correct create_invoice parameter structure: detail.currency_code, primary_recipients[0].billing_info.email_address, items[].quantity as string, unit_amount.currency_code + value as strings
    - Confirmed invoice ID parsed from createResult.href.split("/")[-1] (NOT from result["id"])
    - Confirmed send_invoice_reminder accepts optional "note" parameter
    - Confirmed create_agent from langchain.agents accepts system_prompt; returns CompiledStateGraph with .invoke() and .stream()
    - Confirmed delete_invoice does NOT exist in paypal-agent-toolkit==1.1.0
    - _Acceptance criteria: MET — all tool names and parameter schemas confirmed; documented in spike_results.md_

  - [~] 0.2 Live sandbox and Gemini tool-calling verification (PENDING — blocked on credentials)
    - Create .env from .env.example with real PAYPAL_CLIENT_ID, PAYPAL_SECRET, GOOGLE_API_KEY, GEMINI_MODEL=gemini-2.0-flash
    - Enable invoicing on PayPal sandbox seller account (Developer Dashboard > Sandbox Accounts > seller > Enable Invoicing)
    - Run live create_invoice call using corrected parameter structure; confirm createResult.href contains valid invoice ID
    - Run live Gemini tool-calling test; confirm propose_create_invoice and lookup_client_email are called by the agent
    - _Acceptance criteria: one invoice created and sent in sandbox; Gemini tool calling confirmed live_
    - _Prerequisites: .env credentials available; invoicing enabled on sandbox account_
- [x] 1. Project setup and configuration (P0)
  - [x] 1.1 Create project scaffold and dependency/config templates
    - Create the `invoicepilot/` folder structure per the design Folder Structure: `agent.py`, `app.py`, `config.py`, `models.py`, `client_registry.py`, `paypal_service.py`, `approval.py`, `audit_log.py`, `tools.py`, and a `tests/` directory
    - Create `requirements.txt` with pinned versions: `streamlit`, `langchain` (>=1.0 v1 API), `langchain-google-genai`, `paypal-agent-toolkit`, `pydantic` (>=2.0), `python-dotenv`, `hypothesis`, `pytest`
    - Create `.env.example` with placeholders: `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, `GOOGLE_API_KEY`, `GEMINI_MODEL`
    - Create `clients.json.example` with sample flat entries `{"Rahul": "rahul@example.com"}`
    - Create `.gitignore` with entries for `.env`, `clients.json`, `__pycache__/`, `.pytest_cache/`
    - _Requirements: 12.1, 12.2, 12.3; Design: Folder Structure, Dependencies_

  - [x] 1.2 Implement config.py
    - Load environment variables from `.env` using `python-dotenv`
    - Define constants `AMOUNT_CAP = 1000.00` and `CURRENCY = "USD"`
    - Read `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, `GOOGLE_API_KEY`, `GEMINI_MODEL` from environment
    - Fail fast with a clear message if any required env var is missing at startup
    - _Requirements: 12.1, 12.4; Design: config.py, Component summary_

- [x] 2. Core data models (P0)
  - [x] 2.1 Implement models.py with Pydantic data models
    - Implement InvoiceProposal with proposal_id (UUID4), action_type="create_invoice", client_name, client_email, amount as Decimal (gt=0 le=AMOUNT_CAP), currency default USD, description; field_validators for RFC 5322 email format and currency==USD
    - Implement ReminderProposal with proposal_id (UUID4), invoice_id, client_name, amount_due as Decimal, optional proposed_note
    - Implement AuditLogEntry with timestamp, optional proposal_id for event correlation, action_type Literal, description, optional result
    - Implement `ClientRecord` (`name`, `email`)
    - _Requirements: 2.1, 2.3, 2.6, 5.7, 5.8, 6; Design: Data Models_

  - [x] 2.2 Write property test for amount cap and currency invariant
    - **Property 1: Amount_Cap_and_Currency invariant**
    - **Validates: Requirements 2.1, 2.3, 2.6**
    - Generate random float amounts (negatives, zero, >1000, edge cases 999.99 and 1000.01) with Hypothesis; assert that after validation the accepted amount satisfies `0 < amount <= 1000.00` and rejected amounts do not pass, and that currency always equals `"USD"`
    - Test `models.py` validation directly with no PayPal calls
    - _Requirements: 2.6; Design: Correctness Properties, Testing Strategy_

- [ ] 3. Client registry service (P0)
  - [x] 3.1 Implement client_registry.py
    - Implement `load_clients()` returning a flat `{"name": "email"}` dict from `clients.json` (per OQ-1 design assumption)
    - Implement `lookup_email(name, clients)` with case-sensitive exact match, returning `None` when the name is not found
    - Raise a clear startup error if `clients.json` is missing
    - _Requirements: 1.2, 1.3, 11.3; Design: Component 5_

  - [~] 3.2 Write unit tests for client registry
    - Test name-to-email lookup (found), missing client returns `None`, and empty registry
    - Test case sensitivity (exact match only, no fuzzy matching)
    - _Requirements: 1.2, 1.3; Design: Component 5_

- [x] 4. Audit log service (P0)
  - [x] 4.1 Implement audit_log.py
    - Implement `add_entry(audit_log, action_type, description, result=None)` that appends an `AuditLogEntry` with a UTC timestamp to the session-state list
    - Support `action_type` values: `proposed`, `approved`, `rejected`, `executed`, `error`
    - In-memory session state only, no file persistence (per OQ-6 design assumption)
    - _Requirements: 6.1, 6.2, 6.3, 6.4; Design: Component 8_

  - [x] 4.2 Write property test for audit log completeness
    - **Property 4: Audit_Log completeness invariant**
    - **Validates: Requirements 6.1, 6.2, 6.5**
    - Generate random sequences of proposals, approvals, rejections, and executions with Hypothesis; assert every proposal has a `proposed` entry, every approval an `approved` entry, every rejection a `rejected` entry, and every execution an `executed` or `error` entry
    - _Requirements: 6.5; Design: Correctness Properties, Testing Strategy_

- [ ] 5. Custom proposal tools (P0)
  - [x] 5.1 Implement tools.py with custom LangChain proposal tools
    - Implement lookup_client_email (@tool, read-only): look up client email from clients.json via client_registry; return {client_name, client_email} JSON or error JSON if not found; never writes to clients.json or calls PayPal
    - Implement propose_create_invoice (@tool): validate using Decimal (0 < amount <= 1000), RFC 5322 email; return structured JSON with amount as Decimal string; no PayPal API call
    - Implement propose_send_reminder (@tool): return structured JSON with invoice_id, client_name, amount_due as Decimal string, proposed_note; proposed_note is display-only (confirm PayPal note support during spike); no PayPal API call
    - _Requirements: 1.4, 1.5, 2.4, 5.3, 5.7, 5.8, 5.9, 8.4; Design: Component 3_

  - [~] 5.2 Write unit tests for proposal validation
    - Test amount validation with Decimal edge cases (missing, zero, negative, over cap, 999.99, 1000.00, 1000.01)
    - Test RFC 5322 email validation and USD-only currency enforcement
    - Test lookup_client_email: found client returns email JSON, not-found returns error JSON
    - _Requirements: 1.5, 2.4, 5.9; Design: Component 3_

- [x] 6. Agent layer (P0)
  - [x] 6.1 Implement agent.py with create_agent, system prompt, and tool whitelist
    - Build a read-only PayPal toolkit with {invoices: {list: True, get: True}} via PayPalToolkit + Configuration + Context(sandbox=True) (exact key names confirmed from Task 0 spike)
    - Register all_tools = read_tools + [lookup_client_email] + proposal_tools with create_agent(model=ChatGoogleGenerativeAI(model=GEMINI_MODEL), tools=all_tools, system_prompt=...)
    - Implement the strict billing-only system prompt (USD only, never over $1,000, ask for the email if unknown, never invent data, refuse out-of-scope requests such as refunds/deleting/cancelling)
    - NEVER import paypal_service.py or expose any gated/destructive tool to the agent
    - Prerequisites: Task 0.1 (spike) must be complete before this task
    - _Requirements: 1.1, 5.1, 5.2, 5.3, 5.5, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6; Design: Component 2, API Integration Contracts_

  - [x] 6.2 Write property test for tool whitelist conformance
    - **Property 3: Tool_whitelist conformance**
    - **Validates: Requirements 5.1, 5.5, 5.6**
    - Assert the agent's tool list contains only `list_invoices` (+`get_invoice` if available) and the proposal tools; assert no `Never_Exposed_Tool` name (`delete_invoice`, `cancel_sent_invoice`, `record_refund_for_invoice`, `record_payment_for_invoice`, order/subscription tools) appears
    - Static configuration check against the registered tool set
    - _Requirements: 5.6; Design: Correctness Properties, Testing Strategy_

- [x] 7. PayPal write service (P0)
  - [x] 7.1 Implement paypal_service.py (app-controlled write operations)
    - Build a second `PayPalToolkit` with write actions `{"invoices": {"create": True, "sendReminder": True}}` — "send" omitted because create_invoice auto-sends (spike-confirmed); never enable cancel, generateQRC, or order/subscription tools; delete_invoice does not exist in the package
    - Implement `create_and_send_invoice(proposal)`: call `create_invoice` with detail.currency_code, primary_recipients[0].billing_info.email_address, items[].quantity as string; parse invoice ID from createResult.href.split("/")[-1]; no separate send_invoice call; handle malformed response (missing createResult.href) and timeout as distinct error states
    - Implement `send_reminder(invoice_id)` returning `{status:"sent"}` or `{status:"error", error}`
    - Revalidate the proposal (amount cap, currency, email format) before execution as defense in depth
    - This is the ONLY component with write-tool access; must not be imported by agent.py or tools.py
    - Prerequisites: Task 0.1 (spike) must be complete before this task
    - _Requirements: 3.3, 3.4, 4.1, 4.2, 4.3, 8.2, 15.1, 15.2; Design: Component 6, API Integration Contracts_

- [x] 8. Approval engine (P0)
  - [x] 8.1 Implement approval.py state machine and execution orchestration
    - Implement approve(proposal, session_state, audit_log): check proposal_state not in (executing, completed) as duplicate rejection guard; set proposal_state=executing before any PayPal call; revalidate with Decimal; dispatch to paypal_service; log all events with proposal_id
    - Implement `reject(proposal, audit_log)`: log `rejected`, return `{status:"rejected"}`
    - Implement the state machine: PENDING -> EXECUTING -> COMPLETED | TIMEOUT_AMBIGUOUS | ERROR, and PENDING -> REJECTED. TIMEOUT_AMBIGUOUS covers both network timeouts and malformed responses after a PayPal write was attempted. ERROR is only for pre-execution failures where no PayPal write occurred.
    - Three failure modes: (A) definite pre-execution failure (revalidation, auth error before any PayPal write) - set proposal_state=error, re-enable both buttons, safe to retry; (B) malformed or unexpected create_invoice response after a PayPal write was attempted (createResult.href missing or unparseable) - set proposal_state=timeout_ambiguous (NOT error, because the outcome is unknown and a retry could create a duplicate invoice), keep Approve disabled, no retry; (C) network timeout (outcome unknown) - set proposal_state=timeout_ambiguous, keep Approve disabled, no automatic retry, no duplicate invoice creation
    - Reject on a timeout_ambiguous or malformed_response proposal only dismisses the UI card. It does NOT resolve or cancel the PayPal transaction. A new proposal is allowed only after the user independently verifies and resolves the original PayPal outcome in the sandbox dashboard.
    - _Requirements: 3.3, 3.4, 3.5, 3.7, 6.1, 6.2, 6.4, 8.2, 8.3; Design: Component 7_

  - [x] 8.2 Write property test for approval gate invariant
    - **Property 2: Approval_gate invariant**
    - **Validates: Requirements 3.3, 3.5, 3.6**
    - Generate random interaction sequences (no approve, approve once, approve twice) with Hypothesis; assert no gated PayPal write tool is invoked unless Approve is clicked exactly once
    - Mock the PayPal write tools and verify call counts
    - _Requirements: 3.6; Design: Correctness Properties, Testing Strategy_
  - [x] 8.3 Write unit tests for approval engine state transitions (P0)
    - Test state machine transitions: PENDING -> EXECUTING -> COMPLETED, TIMEOUT_AMBIGUOUS, ERROR, REJECTED
    - Test duplicate rejection guard: Approve on an EXECUTING proposal returns duplicate_rejected
    - Test duplicate rejection guard: Approve on a COMPLETED proposal returns duplicate_rejected
    - Test duplicate rejection guard: Approve on a TIMEOUT_AMBIGUOUS proposal returns duplicate_rejected (critical — must never re-execute a PayPal call with unknown prior outcome)
    - Test duplicate rejection guard: Approve on a REJECTED proposal returns duplicate_rejected
    - Test reject() sets proposal_state to rejected regardless of prior state (including timeout_ambiguous)
    - Test that after Reject on a timeout_ambiguous proposal, a subsequent Approve is blocked
    - Test failure mode A: revalidation failure sets proposal_state=error and re-enables buttons without calling PayPal
    - Test failure mode B: malformed create_invoice response (after PayPal write attempted) sets proposal_state=timeout_ambiguous (NOT error), Approve stays disabled, no retry possible, audit log entry written
    - Test failure mode C: timeout sets proposal_state=timeout_ambiguous, no PayPal retry issued, audit log entry written
    - _Acceptance criteria: all guard states verified, no duplicate PayPal call possible from any terminal state_
    - _Requirements: 3.5, 3.6, 3.7; Design: Component 7, Approval Engine state machine, Testing Strategy_

- [ ] 9. Streamlit UI (P0)
  - [x] 9.1 Implement app.py session state and chat interface
    - Initialize session state keys: `messages`, `pending_proposal`, `audit_log`, `proposal_state`
    - Render the Streamlit chat interface; on submit invoke the agent graph and stream the response
    - Implement `extract_proposal(result)` scanning `ToolMessage` objects for `propose_create_invoice`/`propose_send_reminder` JSON, storing a valid proposal as `pending_proposal`
    - _Requirements: 16.1, 5.9; Design: Component 1, Session state keys_

  - [x] 9.2 Implement approval card rendering and approve/reject handlers
    - Render the Approval_Card from the pending proposal showing client name, client email, amount (USD), and description, with Approve and Reject buttons
    - On Approve: disable both buttons (prevent double-click), call `approval.approve(proposal)`, display the PayPal invoice number and status
    - On Reject: dismiss the card, call `approval.reject(proposal)`, write a rejected entry to the audit log
    - Enforce one pending proposal at a time (OQ-5): auto-reject and log any older pending proposal when a new chat message arrives
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 4.1, 4.2, 4.3, 5.9, 8.1; Design: Component 1, Sequence Diagrams_

  - [~] 9.3 Implement audit log panel and error handling in UI
    - Render audit log entries from `st.session_state["audit_log"]` on screen
    - Handle PayPal errors (auth, invoicing-not-enabled, validation): show a readable message and log an `error` entry
    - Handle Gemini errors/rate limits: show a retry message, keep the UI functional, support manual retry by resending the chat message (OQ-10)
    - _Requirements: 6.3, 11.1, 11.2, 11.4, 17.1, 17.2; Design: Component 1, Error Handling matrix_

- [~] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Project deliverables (P0)
  - [~] 11.1 Write README.md
    - Setup steps, required keys (`PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, `GOOGLE_API_KEY`, `GEMINI_MODEL`), and run instructions (`streamlit run app.py`)
    - Enable a judge to set up and run the project in approximately 5 minutes
    - _Requirements: 14.1, 14.2, 16.2; Design: Folder Structure_

  - [~] 11.2 Write LICENSE and FEATURES.md
    - Add the MIT `LICENSE` file
    - Write `FEATURES.md` text description of features and functionality for the hackathon submission
    - _Requirements: 14.3, 14.5; Design: Folder Structure_

- [~] 12. Checkpoint - Final verification
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. P1 - Check-in for unpaid invoices
  - [~] 13.1 Implement batch overdue reminder proposals
    - Extend the agent system prompt to support "check my unpaid invoices": call `list_invoices`, identify overdue invoices (status `SENT` with `due_date < today` per the OQ-2 status mapping), and propose a reminder for each overdue invoice
    - Render multiple reminder Approval_Cards, each requiring individual Approve/Reject; an approved reminder triggers `send_invoice_reminder` for that invoice only
    - Report only data returned by the PayPal tools; never invent invoice numbers, amounts, or statuses
    - _Requirements: 7.1, 7.2, 7.3, 9.1, 9.2, 9.3; Design: Status Mapping (OQ-2), Component 1_

- [ ] 14. P2 - Earnings dashboard
  - [~] 14.1 Implement earnings dashboard with get_merchant_insights
    - Register the `get_merchant_insights` read-only tool in the agent toolkit only when the P2 feature is enabled
    - Display earnings insights from `get_merchant_insights` or `list_transactions`
    - _Requirements: 5.1, 10.1; Design: Component 2, Correctness Properties note_

## Notes

- All property-based tests (tasks 2.2, 4.2, 5.2, 6.2, 8.2, and new 8.3) are P0 MANDATORY and must pass before checkpoint tasks. They cannot be skipped.
- Each task references specific requirements for traceability to the requirements document.
- Checkpoints ensure incremental validation; Task 0.1 (spike) is a HARD PREREQUISITE for tasks 6.1 and 7.1. The spike must confirm tool names, configuration keys, and Gemini tool calling before agent and service implementation begins. Do not skip.
- The implementation language is Python (the design specifies Python throughout, not pseudocode).
- Cut order from the PRD: P2 (earnings dashboard) first, then P1 (check-in), then UI polish. Never cut: the approval gate, the README, the video. (The demo video is a non-code deliverable and is intentionally outside this task list.)
- PBT and unit tests use mocked PayPal/Gemini; live integration tests against the sandbox are optional and gated behind credentials (`@pytest.mark.integration`).
- Property tests are placed close to the implementation they verify to catch errors early.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1"] },
    { "id": 1, "tasks": ["1.1", "1.2", "2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.1", "5.1", "7.1"] },
    { "id": 3, "tasks": ["4.2", "5.2", "6.1", "8.1"] },
    { "id": 4, "tasks": ["6.2", "8.2", "8.3", "9.1"] },
    { "id": 5, "tasks": ["9.2"] },
    { "id": 6, "tasks": ["9.3"] },
    { "id": 7, "tasks": ["11.1", "11.2", "13.1"] },
    { "id": 8, "tasks": ["14.1"] }
  ]
}
```
