# DEMO_VIDEO_SCRIPT.md
# InvoicePilot – AI-Powered Billing Assistant
# Hackathon Demo Video Script & Storyboard
# Target duration: 3:00 minutes (180 seconds)

---

## Project Quick Reference (for recording accuracy)

| Item | Actual value |
|------|-------------|
| App command | streamlit run app.py |
| Demo client | Rohit |
| Demo amount | \.00 USD |
| Demo description | logo design, quantity 1 |
| AI model | Gemini 2.5 Flash (via ChatGoogleGenerativeAI) |
| Agent framework | LangChain create_agent → CompiledStateGraph |
| PayPal mode | Sandbox only |
| Write protection | All PayPal writes require explicit Approve click |
| Tools the LLM sees | list_invoices, get_invoice, lookup_client_email, propose_create_invoice, propose_send_reminder |
| Tools the LLM CANNOT call | create_invoice, send_invoice, send_invoice_reminder, cancel_sent_invoice |

---

## SCENE 1 — The Problem (0:00–0:20)
**Duration:** 20 seconds

### Visual direction
- Black screen fading in to dark slate background (#0F172A)
- Three floating "task cards" drift across the screen, each with a red checkmark becoming an X
- Cards read: "Write invoice → Send email → Follow up → Repeat"
- Subtle parallax animation; no stock footage

### On-screen text sequence
1. (0:00) Opening line, large white serif:
   **"Freelancers shouldn't spend their time managing invoices."**
2. (0:08) Smaller sans-serif below:
   *"They should spend it doing the work they love."*
3. (0:14) Three pain-point pills slide in from left:
   - 🕐 Manually looking up client details
   - 📄 Formatting invoices every time
   - 📬 Chasing late payments manually

### Voiceover (0:00–0:20)
> "Every freelancer knows this feeling — a great project is done, but before you can collect, there's a pile of admin: look up the client's email, write the invoice, send it, then wait, and follow up when it's late. It's repetitive, it's tedious, and it's time you're not billing for."

### Transition
Soft wipe left into Scene 2. The last pain-point card morphs into the InvoicePilot logo.

---

## SCENE 2 — Introducing InvoicePilot (0:20–0:40)
**Duration:** 20 seconds

### Visual direction
- Logo and app name appear center screen
- Logo: a stylised invoice page with a robot/lightning bolt icon
- Background shifts to deep navy (#0E1E3D) with a subtle gradient
- Tagline slides up from below

### On-screen text
1. App name (large, white bold):
   **🧾 InvoicePilot**
2. Tagline below:
   *"Your AI billing assistant. Your control over every transaction."*
3. Three feature pills slide in one by one (0:28–0:36):
   - 💬 Chat-based billing interface
   - 🤖 Gemini-powered AI reasoning
   - ✅ Human-in-the-loop approval

### Voiceover (0:20–0:40)
> "Introducing InvoicePilot — a chat-based billing agent built for freelancers. You simply describe what you want. InvoicePilot's AI understands your request, looks up your client, prepares the invoice proposal — and then stops. Because every payment action requires your explicit approval. The AI proposes. You decide. The app executes."

### Transition
Zoom into centre of screen, transitioning to a live screen recording of the Streamlit app.

---

## SCENE 3 — Live Invoice Creation (0:40–1:20)
**Duration:** 40 seconds

### Screen recording instructions
- Resolution: 1920×1080, app maximised in browser
- Zoom level: 100%
- Hide browser bookmarks bar
- Record the full Streamlit app at http://localhost:8501
- Cursor should move deliberately; no jitter

### Recording steps — do exactly this sequence
1. App is open with empty chat history
2. Click the chat input box at the bottom
3. Type slowly (or use a text expander for smooth appearance):
   **"Create an invoice for Rohit for \ for logo design, quantity 1."**
4. Press Enter / click Send
5. Wait for the AI response — allow it to load fully
6. The agent MUST call lookup_client_email and return a proposal
7. The proposal card should appear showing:
   - Client: Rohit
   - Email: sb-ugjvm53903701@personal.example.com *(blur/mask the last 10 chars in editing)*
   - Amount: \.00 USD
   - Description: logo design, quantity 1

### Zoom instructions
- 2× zoom on the chat input while typing
- Pull back to full view as the AI responds
- 2× zoom on the proposal card to show each field clearly

### Captions to add in editing
- (0:42) CAPTION: "Plain English request — no forms, no templates"
- (0:52) CAPTION: "AI automatically looks up Rohit's email from the client registry"
- (1:00) CAPTION: "Invoice proposal generated — not yet sent"
- (1:12) CAPTION: "Every field confirmed before execution"

### Voiceover (0:40–1:20)
> "Let's see it in action. I'll type a simple request: 'Create an invoice for Rohit for three hundred dollars for logo design.' InvoicePilot's Gemini-powered agent parses the request, automatically calls the client registry to retrieve Rohit's email address — without asking me — and builds a structured invoice proposal. Notice that at this point, nothing has been sent to PayPal. The AI has only proposed. I can review every field: client name, email, amount, and description. Only when I'm satisfied will I proceed."

### Transition
Hold on the proposal card, then zoom into the Approve button.

---

## SCENE 4 — Human Approval and PayPal Integration (1:20–1:55)
**Duration:** 35 seconds

### Screen recording instructions
- Remain on the Streamlit app from Scene 3
- The proposal card should still be visible

### Recording steps
1. Hover over the **✅ Approve** button (pause 1 second)
2. Click Approve
3. Both buttons become disabled immediately (shows "Executing…" state)
4. Wait for the PayPal call to complete
5. Success state shows:
   - ✅ Completed
   - Invoice ID (e.g. INV2-XXXX-XXXX-XXXX-XXXX)
6. The Audit Log expander at the bottom shows entries:
   - proposed: create_invoice for Rohit
   - approved: create_invoice for Rohit
   - executed: Invoice INV2-XXXX — sent

### Zoom instructions
- Tight zoom (3×) on the Approve button at the moment of click
- Zoom out slowly to show the disabled "Executing…" state
- Zoom in on the success message and invoice ID
- Open the Audit Log expander and zoom on the entries

### Captions to add in editing
- (1:20) CAPTION: "Review complete — ready to approve"
- (1:25) CAPTION: "One click. No automatic execution."
- (1:32) CAPTION: "Approval engine: validate → execute → audit"
- (1:40) CAPTION: "Invoice created AND sent in a single atomic PayPal call"
- (1:48) CAPTION: "Full audit trail: proposal → approval → execution"

### Architecture callout (1:35–1:45)
Overlay a simple diagram (can be a static image created in advance):

`
   LLM (Gemini)         App Layer            PayPal Sandbox
  ─────────────        ─────────────        ─────────────
  Propose only    →    You click Approve  → create_invoice
  CANNOT write    ✗    approval.py        → Invoice SENT
`

Caption: **"The LLM cannot call PayPal write operations — ever."**

### Voiceover (1:20–1:55)
> "I click Approve. The approval engine immediately validates the proposal against the same rules — amount cap, currency, email format — before making any PayPal call. Notice both buttons are disabled the moment I click, preventing any duplicate submission. The application calls PayPal's create_invoice API, which creates and sends the invoice in a single operation. We get back the invoice ID, and the audit log captures every step: proposed, approved, executed. The AI could not have done this on its own. That's by design."

### Transition
Cut to PayPal Sandbox browser tab.

---

## SCENE 5 — Buyer Payment (1:55–2:25)
**Duration:** 30 seconds

### Screen recording instructions
- Switch to a browser showing the PayPal Sandbox dashboard
- Log into the Business (Seller) sandbox account
- Navigate to Invoicing section
- Keep all credentials and account numbers out of frame

### Recording steps — Business account view
1. Show the Invoicing dashboard
2. The invoice appears with status: **SENT** (or awaiting payment)
3. Click on the invoice to show details:
   - Amount: \.00
   - Recipient: (blurred email)
   - Status: Awaiting Payment

### Recording steps — Buyer payment
4. Open a new browser tab (or incognito window)
5. Log into the Personal (Buyer) sandbox account
6. Navigate to Activity → find the invoice notification
7. Click **Pay Now** (or **Pay Invoice**)
8. Complete the \.00 payment using sandbox balance
9. Payment confirmation screen appears

### Privacy rules — CRITICAL
- Blur all email addresses (use Gaussian blur in editor)
- Blur all account numbers, transaction IDs after first 4 chars
- Never show Client ID, Client Secret, or API keys
- Do not show PayPal password entry screen

### Captions to add in editing
- (1:55) CAPTION: "PayPal Sandbox — Seller (Business) Account"
- (2:00) CAPTION: "Invoice created and delivered to buyer"
- (2:08) CAPTION: "Buyer receives invoice — no manual email needed"
- (2:18) CAPTION: "Buyer completes \ payment"

### Voiceover (1:55–2:25)
> "Switching to the PayPal Sandbox dashboard, we can see the invoice has arrived in the seller account. The buyer — using their own sandbox account — receives the invoice directly in their PayPal dashboard. No manual email, no PDF attachment, no chasing. The buyer clicks Pay Now and completes the three hundred dollar payment. All within the PayPal Sandbox environment."

### Transition
Cut back to Streamlit app, showing a fresh chat session.

---

## SCENE 6 — Final Verification (2:25–2:45)
**Duration:** 20 seconds

### Screen recording instructions
- Return to Streamlit app
- Type in chat: **"Check my invoices"** or **"What's the status of my invoices?"**
- The agent should call list_invoices and return the status

### Expected output from agent
The agent calls list_invoices (read-only) and reports:
- Invoice INV2-XXXX
- Status: PAID
- Amount: \.00
- Amount due: \.00

### Fallback if live response is unavailable
If the agent response is delayed or incomplete, use a pre-recorded clip of:
- The agent response showing invoice status
- Alternatively, show the PayPal dashboard directly

### Captions to add in editing
- (2:25) CAPTION: "Back in InvoicePilot — checking payment status"
- (2:30) CAPTION: "Agent reads invoices — no write access, ever"
- (2:38) CAPTION: "Invoice paid. \. Amount due: \."

### Voiceover (2:25–2:45)
> "Back in InvoicePilot, I can ask the agent to check my invoice status. It calls the PayPal API in read-only mode — it can never make changes — and reports that the invoice has been paid. Three hundred dollars, amount due zero. The full cycle: request, propose, approve, send, pay, confirm — all in under three minutes."

### Transition
Fade to dark. Hold 1 second. Fade in closing screen.

---

## SCENE 7 — Closing (2:45–3:00)
**Duration:** 15 seconds

### Visual direction
- Deep dark background (#070F1E)
- InvoicePilot logo fades in centre
- Tagline appears below
- Technology stack appears below that in smaller text
- Subtle glow effect around logo

### On-screen text
1. (2:45) Logo + app name:
   **🧾 InvoicePilot**
2. (2:48) Tagline (white, medium):
   **"Intelligent Billing. Human-Controlled Payments."**
3. (2:52) Stack line (smaller, grey):
   Python  |  Streamlit  |  LangChain  |  Gemini  |  PayPal API
4. (2:56) Hackathon label:
   *Built for the PayPal AI Hackathon*

### Voiceover (2:45–3:00)
> "InvoicePilot. Intelligent billing, with human-controlled payments. Built on Python, Streamlit, LangChain, Gemini, and the PayPal Agent Toolkit. The AI does the thinking. You make the decisions. Thank you."

### Music/audio notes
- Fade out voiceover gently over last 3 seconds
- Optional: subtle upbeat outro sting (royalty-free only; no copyrighted music)

---

## FULL VOICEOVER SCRIPT (continuous read)

> "Every freelancer knows this feeling — a great project is done, but before you can collect, there's a pile of admin: look up the client's email, write the invoice, send it, then wait, and follow up when it's late. It's repetitive, it's tedious, and it's time you're not billing for.
>
> Introducing InvoicePilot — a chat-based billing agent built for freelancers. You simply describe what you want. InvoicePilot's AI understands your request, looks up your client, prepares the invoice proposal — and then stops. Because every payment action requires your explicit approval. The AI proposes. You decide. The app executes.
>
> Let's see it in action. I'll type a simple request: 'Create an invoice for Rohit for three hundred dollars for logo design.' InvoicePilot's Gemini-powered agent parses the request, automatically calls the client registry to retrieve Rohit's email address — without asking me — and builds a structured invoice proposal. Notice that at this point, nothing has been sent to PayPal. The AI has only proposed. I can review every field: client name, email, amount, and description. Only when I'm satisfied will I proceed.
>
> I click Approve. The approval engine immediately validates the proposal against the same rules — amount cap, currency, email format — before making any PayPal call. Notice both buttons are disabled the moment I click, preventing any duplicate submission. The application calls PayPal's create_invoice API, which creates and sends the invoice in a single operation. We get back the invoice ID, and the audit log captures every step: proposed, approved, executed. The AI could not have done this on its own. That's by design.
>
> Switching to the PayPal Sandbox dashboard, we can see the invoice has arrived in the seller account. The buyer — using their own sandbox account — receives the invoice directly in their PayPal dashboard. No manual email, no PDF attachment, no chasing. The buyer clicks Pay Now and completes the three hundred dollar payment. All within the PayPal Sandbox environment.
>
> Back in InvoicePilot, I can ask the agent to check my invoice status. It calls the PayPal API in read-only mode — it can never make changes — and reports that the invoice has been paid. Three hundred dollars, amount due zero. The full cycle: request, propose, approve, send, pay, confirm — all in under three minutes.
>
> InvoicePilot. Intelligent billing, with human-controlled payments. Built on Python, Streamlit, LangChain, Gemini, and the PayPal Agent Toolkit. The AI does the thinking. You make the decisions. Thank you."

---

## TRANSITION AND ANIMATION GUIDE

| Transition | From → To | Style | Duration |
|-----------|-----------|-------|----------|
| T1 | Scene 1 → 2 | Soft wipe left; pain card morphs to logo | 0.5s |
| T2 | Scene 2 → 3 | Zoom into screen centre, blur into screen recording | 0.6s |
| T3 | Scene 3 → 4 | Hold; zoom onto Approve button | 0.3s |
| T4 | Scene 4 → 5 | Cut; brief flash to PayPal tab | 0.2s |
| T5 | Scene 5 → 6 | Cut back to Streamlit; alt-tab animation | 0.3s |
| T6 | Scene 6 → 7 | Fade to black 0.5s; then logo fade-in | 1.0s |

**Architecture overlay (Scene 4, 1:35–1:45):**
Create a static slide in advance with a 3-column flow:
- Column 1 (green border): LLM — propose_create_invoice only
- Arrow: "structured JSON proposal"
- Column 2 (blue border): App — pproval.approve()
- Arrow: "after Approve click"
- Column 3 (red border): PayPal — create_invoice → SENT

---

## EDITING INSTRUCTIONS

### Software recommendations
- **OBS Studio** — free screen recording (1080p60)
- **DaVinci Resolve** (free tier) — editing, colour grading, text overlays
- Alternatively: **Kdenlive** (free, cross-platform)

### Colour palette for text overlays
- Background: #070F1E (deep navy)
- Primary text: #FFFFFF (white)
- Accent: #3B82F6 (blue) for feature pills
- Success green: #22C55E for "Approved" / "Paid" callouts
- Warning amber: #F59E0B for timeout notices

### Caption style
- Font: Inter or Roboto (system font)
- Size: 28–32pt for major captions, 20pt for sub-captions
- Position: lower third, 10% from bottom
- Background: semi-transparent dark pill (#000000 at 60% opacity)
- Fade in: 0.2s; hold 2–3s; fade out 0.2s

### Screen recording colour grading
- Apply slight vignette to screen recordings
- Increase contrast by 10–15% to aid readability
- Keep zoom animations smooth: ease-in-out, 0.4s

### Audio
- Voiceover: record in a quiet room; use a headset microphone
- Normalize audio to –14 LUFS
- Apply gentle noise reduction
- No background music during screen recording scenes (distracting)
- Optional subtle ambient pad under Scene 1 and Scene 7 only
- ALL music must be royalty-free (e.g., ccMixter, Pixabay Music)
- No copyrighted music — hackathon rules prohibit it

### Export settings
- Format: MP4 (H.264)
- Resolution: 1920×1080
- Frame rate: 30fps
- Audio: AAC 192 kbps stereo
- Target file size: under 500 MB

---

## PRIVACY AND SECURITY CHECKLIST (see also DEMO_RECORDING_CHECKLIST.md)

Before exporting the final video, verify EVERY frame:

- [ ] No PayPal Client ID visible (any string starting with A/B + 80 chars)
- [ ] No PayPal Client Secret visible
- [ ] No GOOGLE_API_KEY visible
- [ ] All sandbox email addresses blurred (or masked with ████)
- [ ] No PayPal account passwords visible during login
- [ ] .env file never on screen
- [ ] No real customer data — Rohit is fictional; sandbox email is test-only
- [ ] Audit log proposal IDs (UUID format) are acceptable to show
- [ ] Invoice ID (INV2-XXXX-XXXX-XXXX-XXXX) is acceptable to show
- [ ] No real financial transactions — all sandbox

---

## WHAT IS ACTUALLY IMPLEMENTED (accuracy guide for recording)

The following features are real and can be shown:

| Feature | Implementation | File |
|---------|---------------|------|
| Chat interface | Streamlit st.chat_message / st.chat_input | pp.py |
| Client email lookup | lookup_client_email @tool → clients.json | 	ools.py, client_registry.py |
| Invoice proposal | propose_create_invoice @tool → structured JSON | 	ools.py |
| Approval card | Rendered from pending_proposal in session state | pp.py |
| Approve/Reject buttons | handle_approve() / handle_reject() | pp.py |
| Duplicate click guard | Buttons disabled; state machine guard in pproval.py | pproval.py |
| PayPal create+send | create_and_send_invoice() → single PayPal call | paypal_service.py |
| Audit log panel | Collapsible expander; entries in session state | pp.py, udit_log.py |
| Invoice listing | list_invoices read-only tool | gent.py, PayPal toolkit |
| ,000 cap | Enforced in 	ools.py and paypal_service.py | Both |
| USD-only | Enforced in models + proposal tools | models.py, 	ools.py |

The following are NOT yet implemented (do not show):
- Batch overdue reminder proposals (P1)
- Earnings dashboard (P2)
- Multi-proposal pending queue (P1)
