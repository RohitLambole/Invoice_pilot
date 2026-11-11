# Requirements Document

## Introduction

InvoicePilot is a chat-based billing agent for independent freelancers who invoice international clients. A freelancer types a natural-language message such as "Invoice Rahul $300 for logo design". A Gemini-powered LangChain agent turns the message into a structured invoice draft, and the PayPal sandbox is used to create and send the invoice only after the freelancer explicitly approves the draft. The agent can also list invoices, summarise unpaid/overdue/paid invoices, and propose payment reminders, each of which also requires explicit approval before any PayPal write tool executes.

The defining principle is human-in-the-loop approval: the LLM may freely call read-only PayPal tools, but every money-moving action (create, send, remind) is returned as a proposal and only the application code, triggered by an Approve button, executes the gated PayPal tools. The system is scoped to the PayPal sandbox, USD only, single currency, no database (PayPal is the source of truth), no user accounts, and no autonomous or scheduled actions.

This document captures functional and non-functional requirements derived from the Product Requirements Document (docs/PRD-extracted.md), preserves the P0/P1/P2 priority scheme, and flags every ambiguity as an Open Question rather than resolving it silently.

## Glossary

- **InvoicePilot_App**: The Streamlit single-page application that renders the chat interface, Approval_Cards, and Audit_Log, and holds conversation and pending drafts in session state. The application code that executes gated PayPal tools after approval.
- **InvoicePilot_Agent**: The LangChain agent in agent.py built with `create_agent` and `ChatGoogleGenerativeAI` (Gemini_Model). Returns write actions as proposals and may call read-only PayPal tools freely.
- **UI**: The Streamlit chat interface rendered by InvoicePilot_App, including chat messages, Approval_Cards, and the Audit_Log panel.
- **Freelancer**: The single human user of InvoicePilot; an independent freelancer who invoices international clients and approves or rejects every proposed action.
- **Client_Registry**: The `clients.json` file that maps client names to client email addresses.
- **Invoice_Draft**: A structured proposal produced by the InvoicePilot_Agent containing client name, client email, amount in USD, and description, rendered as an Approval_Card for approval.
- **Approval_Card**: A UI element that displays the Invoice_Draft fields (client name, client email, amount in USD, description) and provides Approve and Reject buttons.
- **Audit_Log**: The on-screen log in the UI that records every proposed action and every executed action.
- **PayPal_Toolkit**: The `paypal-agent-toolkit` configured with invoice tools, used by InvoicePilot_App to execute gated PayPal operations against the PayPal sandbox.
- **Gemini_Model**: The `ChatGoogleGenerativeAI` model named by the `GEMINI_MODEL` environment variable, used by the InvoicePilot_Agent.
- **Read-Only_Tools**: The PayPal tools the InvoicePilot_Agent may call freely: `list_invoices` and `get_invoice`. The `get_merchant_insights` tool is read-only but is registered only when the P2 Earnings_Dashboard feature is implemented.
- **Gated_Tools**: The PayPal tools that execute only after approval via application code: `create_invoice` (spike-confirmed: auto-creates and auto-sends in one call) and `send_invoice_reminder`. Note: `send_invoice` exists in the toolkit but is NOT used for new invoice creation — calling it after `create_invoice` would send a duplicate.
- **Never_Exposed_Tools**: PayPal tools the InvoicePilot_Agent must never access: `cancel_sent_invoice`, `generate_invoice_qr_code`, `record_refund_for_invoice`, `record_payment_for_invoice`, and all order and subscription tools. Note: `delete_invoice` does not exist in `paypal-agent-toolkit==1.1.0` — it is not available to exclude.
- **Tool_Whitelist**: The complete set of PayPal tools exposed to the InvoicePilot_Agent, limited to Read-Only_Tools. Gated_Tools are executed by InvoicePilot_App, not the agent.
- **Amount_Cap**: The maximum allowed invoice amount of $1,000.00 USD; a hard block enforced before any Invoice_Draft can be approved.
- **Invoice_Status_Group**: The summarisation categories the InvoicePilot_Agent reports: unpaid, overdue, and paid. (See Open Question OQ-2 for the mapping to PayPal statuses.)

## Requirements

### Requirement 1: Chat-to-Draft Invoice Extraction — P0

**User Story:** As a Freelancer, I want to type a natural-language billing request and receive a structured Invoice_Draft, so that I avoid manually filling out invoice forms.

#### Acceptance Criteria

1. WHEN the Freelancer submits a chat request containing a client name, an amount, and a description, THE InvoicePilot_Agent SHALL extract the client name, amount, description into an Invoice_Draft.
2. WHEN the InvoicePilot_Agent extracts an Invoice_Draft, THE InvoicePilot_Agent SHALL look up the client name in the Client_Registry to retrieve the client email.
3. IF the client name is not found in the Client_Registry, THEN THE InvoicePilot_Agent SHALL request the client email from the Freelancer before producing an Invoice_Draft.
4. THE InvoicePilot_Agent SHALL populate the Invoice_Draft with the client name, the confirmed client email, the amount in USD, and the description.
5. IF the amount parsed from the request is missing, zero, or negative, THEN THE InvoicePilot_Agent SHALL request a valid amount and SHALL not produce an Invoice_Draft.

### Requirement 2: Amount Cap and Currency Enforcement — P0

**User Story:** As a Freelancer, I want invoice amounts capped at a safe limit and fixed to USD, so that accidental large charges cannot be issued.

#### Acceptance Criteria

1. THE InvoicePilot_App SHALL enforce an Amount_Cap of $1,000.00 USD on every Invoice_Draft.
2. IF an Invoice_Draft amount exceeds $1,000.00 USD, THEN THE InvoicePilot_App SHALL block the draft with a clear message and SHALL not call `create_invoice`.
3. THE InvoicePilot_Agent SHALL use USD as the only supported currency for every Invoice_Draft.
4. THE InvoicePilot_Agent SHALL not propose any Invoice_Draft with an amount greater than $1,000.00 USD.
5. WHEN the Freelancer submits a request with an amount exceeding the Amount_Cap, THE UI SHALL display a clear block message explaining the $1,000.00 USD limit.
6. **Correctness property (PBT):** FOR ALL Invoice_Drafts produced by the InvoicePilot_Agent, the validated amount SHALL satisfy `0 < amount <= 1000.00` and the currency SHALL equal USD. (Amount_cap_and_currency invariant.)

### Requirement 3: Approval Card — P0

**User Story:** As a Freelancer, I want to review a draft's client, email, amount, and description before any money moves, so that I stay in control of billing.

#### Acceptance Criteria

1. WHEN the InvoicePilot_Agent produces an Invoice_Draft, THE UI SHALL render an Approval_Card showing the client name, the client email, the amount in USD, and the description.
2. THE Approval_Card SHALL provide an Approve button and a Reject button.
3. WHEN the Freelancer clicks Approve on an Invoice_Draft, THE InvoicePilot_App SHALL execute `create_invoice` using the Invoice_Draft fields. The `create_invoice` operation creates and sends the invoice in a single call — no separate `send_invoice` call is required or permitted (calling it would send the invoice a second time).
4. WHEN `create_invoice` succeeds, THE UI SHALL display the PayPal invoice number (parsed from the returned href) and the status returned by PayPal.
5. WHEN the Freelancer clicks Approve, THE Approval_Card SHALL disable both the Approve button and the Reject button to prevent duplicate execution on double-click and contradictory interactions.
6. **Correctness property (PBT):** FOR ALL Approval_Card interactions, no gated PayPal tool SHALL execute before the Approve button is clicked exactly once. (Approval_gate invariant.)
7. WHEN the Freelancer clicks Reject on an Approval_Card, THE UI SHALL dismiss the Approval_Card, THE InvoicePilot_App SHALL not execute any Gated_Tool for that Invoice_Draft, and THE InvoicePilot_App SHALL write a rejected decision entry to the Audit_Log.

### Requirement 4: Email Confirmation Before Send — P0

**User Story:** As a Freelancer, I want the client email always visible and confirmed before an invoice is sent, so that invoices never go to the wrong recipient.

#### Acceptance Criteria

1. THE Approval_Card SHALL always display the client email.
2. THE InvoicePilot_App SHALL send an invoice only to the email displayed on the Approval_Card that the Freelancer approved.
3. THE InvoicePilot_App SHALL not send an invoice to any email the Freelancer has not approved on the Approval_Card.

### Requirement 5: Tool Whitelist and Agent Safety — P0

**User Story:** As a Freelancer, I want destructive PayPal tools hidden from the agent and write tools gated behind approval, so that the agent cannot move money or destroy data on its own.

#### Acceptance Criteria

1. THE InvoicePilot_Agent SHALL have access only to the Read-Only_Tools: `list_invoices` and `get_invoice`. The `get_merchant_insights` tool SHALL be registered only when the P2 Earnings_Dashboard feature is implemented.
2. THE InvoicePilot_Agent SHALL call Read-Only_Tools freely without requiring approval.
3. THE InvoicePilot_Agent SHALL return write actions (`create_invoice`, `send_invoice`, `send_invoice_reminder`) as proposals and SHALL not execute those tools directly.
4. THE InvoicePilot_App SHALL execute Gated_Tools only after the Freelancer clicks Approve.
5. THE InvoicePilot_Agent SHALL never be exposed to `cancel_sent_invoice`, `generate_invoice_qr_code`, `record_refund_for_invoice`, `record_payment_for_invoice`, or any order or subscription tools. (`delete_invoice` does not exist in `paypal-agent-toolkit==1.1.0` and requires no exclusion.)
6. **Correctness property (PBT):** FOR ALL agent tool-call traces, no Never_Exposed_Tool SHALL appear in the set of tools the InvoicePilot_Agent invokes. (Tool_whitelist conformance.)
7. WHEN the InvoicePilot_Agent returns a write action as a proposal, THE proposal SHALL be a structured JSON object containing an `action_type` field (one of: `"create_invoice"`, `"send_invoice_reminder"`) and the relevant fields for that action.
8. FOR ALL invoice creation proposals, THE structured JSON SHALL contain `client_name`, `client_email`, `amount`, `currency`, and `description`.
9. THE InvoicePilot_App SHALL parse the structured JSON proposal to render the Approval_Card and SHALL not interpret free-text chat responses as executable proposals.

### Requirement 6: Audit Log — P0

**User Story:** As a Freelancer, I want every proposed and executed action recorded on screen, so that I can review what the agent proposed and what was actually carried out.

#### Acceptance Criteria

1. THE InvoicePilot_App SHALL write every proposed action to the Audit_Log.
2. THE InvoicePilot_App SHALL write every executed action to the Audit_Log.
3. THE Audit_Log SHALL be displayed on screen in the UI.
4. WHEN the Freelancer clicks Approve or Reject, THE InvoicePilot_App SHALL record the decision in the Audit_Log.
5. **Correctness property (PBT):** FOR ALL proposed actions P and executed actions E, every element of E SHALL have a corresponding entry in the Audit_Log, and every element of P SHALL have a corresponding entry in the Audit_Log. (Audit_log completeness invariant.)

### Requirement 7: Invoice Listing and Summarisation — P0

**User Story:** As a Freelancer, I want to see my invoices grouped by unpaid, overdue, and paid, so that I know what needs attention.

#### Acceptance Criteria

1. WHEN the Freelancer requests an invoice listing, THE InvoicePilot_Agent SHALL call `list_invoices` and summarise invoices into the Invoice_Status_Groups: unpaid, overdue, and paid.
2. THE InvoicePilot_Agent SHALL report only the data returned by the PayPal tools and SHALL not invent invoice numbers, amounts, or statuses.
3. THE UI SHALL display the summarised invoice groups to the Freelancer.
4. (Open Question OQ-2: the precise mapping from PayPal invoice statuses to unpaid/overdue/paid is pending clarification.)

### Requirement 8: Reminder Proposal — P0

**User Story:** As a Freelancer, I want to request a reminder for a client with an overdue invoice, so that I can chase late payment without an awkward manual email.

#### Acceptance Criteria

1. WHEN the Freelancer requests a reminder for a client with an overdue invoice, THE InvoicePilot_Agent SHALL produce a proposed reminder for that invoice.
2. WHEN the Freelancer approves the proposed reminder, THE InvoicePilot_App SHALL execute `send_invoice_reminder` for the approved invoice.
3. WHEN the Freelancer rejects the proposed reminder, THE InvoicePilot_App SHALL not execute `send_invoice_reminder`.
4. THE InvoicePilot_Agent SHALL return the reminder as a proposal and SHALL not call `send_invoice_reminder` directly.
5. (Open Question OQ-3: the content and format of the proposed reminder shown to the Freelancer is pending clarification.)

### Requirement 9: Check-In for Unpaid Invoices — P1

**User Story:** As a Freelancer, I want to check all my unpaid invoices and get a reminder proposal for each overdue one, so that I can chase multiple late payers at once.

#### Acceptance Criteria

1. WHEN the Freelancer requests a check of unpaid invoices, THE InvoicePilot_Agent SHALL list the overdue invoices and SHALL propose a reminder for each overdue invoice.
2. THE UI SHALL render each proposed reminder so that each reminder requires individual Approve or Reject.
3. WHEN the Freelancer approves an individual reminder, THE InvoicePilot_App SHALL execute `send_invoice_reminder` for that invoice only.
4. (This requirement is P1 and may be cut per the PRD cut order, keeping "Remind Rahul".)

### Requirement 10: Earnings Dashboard — P2

**User Story:** As a Freelancer, I want to see earnings insights, so that I understand my income at a glance.

#### Acceptance Criteria

1. WHERE the Earnings_Dashboard feature is enabled, THE InvoicePilot_Agent SHALL use `get_merchant_insights` or `list_transactions` to display earnings.
2. (This requirement is P2 and is the first item in the PRD cut order. It may be cut entirely.)

### Requirement 11: Error Handling — P0

**User Story:** As a Freelancer, I want clear error messages and a UI that never crashes, so that I am not blocked by API or model failures.

#### Acceptance Criteria

1. IF the PayPal_Toolkit returns an authentication error, an invoicing-not-enabled error, or a validation error, THEN THE InvoicePilot_App SHALL display a readable message and SHALL write the error to the Audit_Log.
2. IF the Gemini_Model returns an error or a rate-limit response, THEN THE InvoicePilot_App SHALL display a retry message and SHALL not crash the UI.
3. IF the client name is not found in the Client_Registry, THEN THE InvoicePilot_Agent SHALL request the client email from the Freelancer.
4. IF the parsed amount is missing, zero, negative, or exceeds the Amount_Cap, THEN THE InvoicePilot_Agent SHALL not produce an Invoice_Draft and SHALL request or display a corrective message.
5. IF the Invoice_Draft description contains prompt-injection content, THEN the Tool_Whitelist SHALL limit the damage to the tools available to the InvoicePilot_Agent.

### Requirement 12: Configuration and Secrets — P0

**User Story:** As a Freelancer (and hackathon judge), I want configuration via `.env` and example files only in the repo, so that secrets never leak.

#### Acceptance Criteria

1. THE InvoicePilot_App SHALL read PayPal client ID and secret, `GOOGLE_API_KEY`, and `GEMINI_MODEL` from the `.env` file.
2. THE repository SHALL commit only `.env.example` and `clients.json.example`, and SHALL not commit real secrets.
3. THE repository SHALL include `.gitignore` entries for `.env` and real `clients.json`.
4. THE InvoicePilot_App SHALL read `GEMINI_MODEL` from `.env` so that the Gemini_Model can be swapped by changing one configuration value.

### Requirement 13: System Prompt Behaviour — P0

**User Story:** As a Freelancer, I want the agent to follow a strict billing-only system prompt, so that the agent stays within invoicing scope.

#### Acceptance Criteria

1. THE InvoicePilot_Agent SHALL follow the system prompt that defines InvoicePilot as a billing assistant for a freelancer.
2. THE InvoicePilot_Agent SHALL return proposals and SHALL wait for approval rather than creating, sending, or reminding directly.
3. THE InvoicePilot_Agent SHALL use USD only and SHALL not propose an invoice over the Amount_Cap.
4. IF the client email is not known, THE InvoicePilot_Agent SHALL ask for the email before proposing.
5. THE InvoicePilot_Agent SHALL not invent amounts, clients, or invoice numbers.
6. IF a request is outside invoicing such as refunds, deleting, or cancelling, THEN THE InvoicePilot_Agent SHALL respond that the request is outside the supported scope.

### Requirement 14: Readiness and Deliverables — P0

**User Story:** As a hackathon judge, I want a README, example configs, and a short demo video, so that I can run and evaluate the project quickly.

#### Acceptance Criteria

1. THE repository SHALL include a README with setup steps, required keys, and run instructions.
2. THE repository SHALL commit `.env.example` and `clients.json.example`.
3. THE repository SHALL use the MIT license visible in the repo About section.
4. THE project SHALL include a demo video under 3 minutes, publicly accessible on YouTube, in English with no copyrighted music or third-party trademarks, that demonstrates the create, pay, and chase loop including: creating an invoice from a chat prompt, a sandbox buyer paying it, sending an approved reminder for an unpaid invoice, and showing the user attempting to create a $5,000 invoice and InvoicePilot blocking it because the maximum allowed amount is $1,000.
5. THE project SHALL include a text description of features and functionality, separate from the README, as a hackathon submission deliverable.

## Non-Functional Requirements

### Requirement 15: Security — P0

**User Story:** As a Freelancer, I want secrets protected and destructive actions blocked, so that the system is safe to run.

#### Acceptance Criteria

1. THE InvoicePilot_App SHALL store all credentials in `.env` and SHALL not commit real secrets to the repository.
2. THE InvoicePilot_App SHALL execute money-moving Gated_Tools only after explicit approval.
3. THE Tool_Whitelist SHALL exclude all Never_Exposed_Tools from the InvoicePilot_Agent.

### Requirement 16: Usability — P0

**User Story:** As a Freelancer, I want a single clean app and a fast setup, so that I can start billing within minutes.

#### Acceptance Criteria

1. THE UI SHALL render chat, Approval_Cards, and the Audit_Log in a single Streamlit app.
2. THE README SHALL enable a judge to set up and run the project in approximately 5 minutes.

### Requirement 17: Reliability — P0

**User Story:** As a Freelancer, I want the UI to keep working when an external service fails, so that a transient error does not block me.

#### Acceptance Criteria

1. WHILE the Gemini_Model is returning errors or rate-limit responses, THE UI SHALL remain functional and SHALL display a retry message.
2. WHILE the PayPal_Toolkit is returning errors, THE UI SHALL remain functional and SHALL display a readable message.

## User Flows

### Flow A: Create an Invoice

1. The Freelancer submits a chat request such as "Invoice Rahul $300 for logo design."
2. The InvoicePilot_Agent looks up the client name in the Client_Registry. If the client is missing, the agent requests the email.
3. The InvoicePilot_Agent returns a structured Invoice_Draft, and the UI renders the Approval_Card.
4. The Freelancer clicks Approve. The InvoicePilot_App calls `create_invoice` (which creates and sends the invoice in one operation). The UI shows the invoice number and status.
5. The PayPal sandbox buyer opens the invoice email or link and pays.

### Flow B: Check and Chase

1. The Freelancer submits a chat request such as "Check my unpaid invoices."
2. The InvoicePilot_Agent calls `list_invoices`, summarises, and proposes a reminder for each overdue invoice.
3. The Freelancer approves or rejects each reminder. Approved reminders trigger `send_invoice_reminder`.

## Correctness Properties Summary

The following property-based tests target pure application logic (validation, gating, logging, whitelist conformance) and avoid direct testing of external services:

1. **Amount_Cap_and_Currency invariant (Req 2) — P0:** Every produced Invoice_Draft satisfies `0 < amount <= 1000.00` and currency equals USD. Pure validation logic — PBT.
2. **Approval_gate invariant (Req 3) — P0:** No gated PayPal tool executes before Approve is clicked once. Pure gating logic — PBT with mocked PayPal tools.
3. **Tool_whitelist conformance (Req 5) — P0:** No Never_Exposed_Tool appears in agent tool-call traces. Pure conformance check — PBT.
4. **Audit_Log completeness (Req 6) — P0:** Every proposed and executed action has an Audit_Log entry. Pure logging logic — PBT.

Integration tests (not PBT) cover external behavior:
- PayPal sandbox end-to-end (create, send, pay, status): 1-3 representative examples.
- Gemini model tool calling: representative examples with retry behavior.

(Open Question OQ-7: the depth and formality of the test suite is pending clarification.)

## Open Questions and Clarifications Needed

The following ambiguities are identified in the PRD and are NOT resolved silently. Each requires a decision from the Freelancer/product owner before design and implementation.

- **OQ-1 — Client_Registry lookup semantics:** The PRD states `clients.json` maps client names to emails. Clarification needed on: (a) exact JSON structure (e.g., `{"Rahul": "rahul@example.com"}` vs nested objects); (b) case sensitivity of name matching; (c) behaviour when multiple clients share a name; (d) fuzzy or partial name matching. (Req 1, Req 3.)
- **OQ-2 — Invoice_Status_Group mapping:** The PRD asks the agent to summarise invoices as unpaid, overdue, and paid, but does not define how PayPal invoice statuses (e.g., DRAFT, SENT, PAID, CANCELLED, and any due-date field) map to these three groups. Clarification needed on whether "overdue" is `status == SENT AND due_date < today`, and whether "unpaid" includes DRAFT invoices or only SENT invoices. (Req 7.)
- **OQ-3 — Reminder proposal content:** The PRD says "produces a proposed reminder" but does not specify what the Freelancer sees before approving. Clarification needed on whether the proposal shows a drafted reminder message body, which PayPal reminder note/template field is used, and whether the content is agent-generated or fixed text. (Req 8.)
- **OQ-4 — Reject button behaviour (RESOLVED):** Reject dismisses the Approval_Card from the UI, does not execute any Gated_Tool, and writes a rejected decision entry to the Audit_Log. No editing or re-proposing. (Req 3 AC7.)
- **OQ-5 — Multiple pending drafts:** The PRD references "pending drafts" (plural) in session state. Clarification needed on whether multiple Approval_Cards can be pending simultaneously, and how an older draft is treated when a new unrelated chat message arrives. (Req 1, Req 3.)
- **OQ-6 — Audit_Log persistence:** The PRD states "on-screen audit log" and "no database." Clarification needed on whether the Audit_Log is in-memory session state only (lost on refresh) or also mirrored to a file, and what fields each log entry contains (timestamp, action type, details, result). (Req 6.)
- **OQ-7 — Testing scope:** The PRD does not define a test strategy. Clarification needed on the required depth of automated tests, whether unit tests for validation/gating logic are expected, and whether property-based tests are desired beyond the four correctness properties listed. (Correctness Properties Summary.)
- **OQ-8 — Amount input format:** The PRD examples use "$300" but does not specify accepted input formats (e.g., "300", "300 USD", "$300.00", "three hundred"). Clarification needed on which formats the agent must parse and how ambiguous amounts are handled. (Req 1, Req 2.)
- **OQ-9 — Missing description:** The PRD examples always include "for <description>." Clarification needed on behaviour when no description is provided: does the agent ask for one, use an empty description, or reject the draft? (Req 1.)
- **OQ-10 — Gemini retry semantics:** The PRD says "show a retry message" for Gemini errors/rate limits. Clarification needed on whether retry is automatic (and with what backoff/count) or manual via a button. (Req 11, Req 17.)
- **OQ-11 — Repeated reminders:** Clarification needed on whether a reminder can be sent for the same invoice more than once and whether a cooldown is required. (Req 8, Req 9.)
- **OQ-12 — clients.json handling of PII:** Clarification needed on whether `clients.json` (containing client emails, possibly PII) is gitignored and only `clients.json.example` is committed, since the PRD lists `clients.json.example` in the submission checklist without explicitly stating `clients.json` is gitignored. (Req 12.)
- **OQ-13 — Performance targets:** The PRD defines no latency, response-time, or throughput targets. Clarification needed on whether any quantitative performance bounds are required for agent responses or PayPal operations. (Non-functional.)
- **OQ-14 — Invoice field completeness:** The PRD's approval card shows client, email, amount, description. PayPal invoices require additional fields (e.g., billing address, tax, line items, due date). Clarification needed on which PayPal invoice fields are populated and whether defaults are acceptable for the sandbox demo. (Req 1, Req 3.)

## Dependencies and Implementation Risks

### Dependencies
- **paypal-agent-toolkit**: Provides invoice tools against the PayPal sandbox. Version conflicts with the current LangChain are a known risk.
- **LangChain `create_agent`**: Used by agent.py. API surface may change between versions.
- **ChatGoogleGenerativeAI / Gemini_Model**: Model name sourced from `.env` (`GEMINI_MODEL`). Model availability is a known risk (sources conflict on Gemini model retirement).
- **Streamlit**: Single-page UI with session state for conversation and pending drafts.
- **Python**: Runtime and dependency management via pip.

### Risks (from PRD section 14, preserved)
- **Toolkit version conflicts with current LangChain.** Mitigation: do the spike first and pin versions if pip complains.
- **Gemini model availability.** Mitigation: model name in `.env`, test early.
- **Invoicing not enabled on the sandbox app or seller account.** Mitigation: check during the Day 1 spike.
- **Time (about 12 hours total).** Mitigation: small scope and the cut order below.
- **Secrets leak.** Mitigation: `.gitignore` for `.env`, commit `.env.example` only.

### Cut Order (preserved from PRD section 13)
1. Earnings dashboard (P2).
2. Proactive check-in (P1); keep "Remind Rahul" (P0 reminder).
3. UI polish.
Never cut: the approval gate, the README, the video.
