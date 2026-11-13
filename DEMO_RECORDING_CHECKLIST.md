# DEMO_RECORDING_CHECKLIST.md
# InvoicePilot – Hackathon Demo Recording Checklist

---

## PRE-RECORDING SETUP

### Environment
- [ ] Run streamlit run app.py from c:\Users\Asus\OneDrive\Desktop\Invoice_pilot
- [ ] Verify app opens at http://localhost:8501
- [ ] Confirm Gemini API key is working (run python gemini_api-test.py first)
- [ ] Confirm PayPal sandbox credentials are in .env
- [ ] Confirm clients.json has entry: "Rohit": "sb-ugjvm53903701@personal.example.com"
- [ ] Confirm PayPal sandbox seller account has invoicing enabled
- [ ] Confirm PayPal sandbox buyer account country = United States (required for USD invoices)

### Browser preparation
- [ ] Open Chrome or Firefox at 100% zoom
- [ ] Hide bookmarks bar (Ctrl+Shift+B)
- [ ] Close all unrelated tabs
- [ ] Clear browser notifications
- [ ] Set browser to dark mode if available
- [ ] Open two tabs: Tab 1 = InvoicePilot app, Tab 2 = PayPal Sandbox (Seller account)
- [ ] Log into PayPal Sandbox Business (Seller) account in Tab 2 — but do NOT show the login process

### Screen recording software
- [ ] OBS Studio installed and configured
- [ ] Recording resolution: 1920×1080
- [ ] Frame rate: 60fps (or 30fps minimum)
- [ ] Audio: microphone enabled and tested
- [ ] Test recording: 10-second test clip, verify audio sync
- [ ] Disable desktop notifications (Do Not Disturb mode)
- [ ] Disable screensaver and screen sleep

### Practice run
- [ ] Do a full practice run without recording
- [ ] Time the practice run — target 2:50–3:00
- [ ] Confirm the AI responds correctly to: "Create an invoice for Rohit for \ for logo design, quantity 1."
- [ ] Confirm the proposal card shows all fields correctly
- [ ] Confirm Approve button works and returns invoice ID
- [ ] Confirm PayPal sandbox invoice appears in seller dashboard

---

## SCENE-BY-SCENE RECORDING CHECKLIST

### Scene 1 — Problem intro (0:00–0:20)
- [ ] This scene is motion graphics only — no live recording needed
- [ ] Create in DaVinci Resolve or Canva using the script text
- [ ] Background colour: #0F172A
- [ ] Text animations: fade in, 0.3s delay between each pill

### Scene 2 — App introduction (0:20–0:40)
- [ ] This scene is motion graphics only — no live recording needed
- [ ] Show InvoicePilot logo/title (use the app header from a screenshot)
- [ ] Three feature pills animate in one by one

### Scene 3 — Live invoice creation (0:40–1:20)
- [ ] App is open with empty chat history
- [ ] No previous proposals pending
- [ ] Proposal_state = "pending" (clean state)
- [ ] Type the full request: "Create an invoice for Rohit for \ for logo design, quantity 1."
- [ ] Wait for AI to complete — do not cut during thinking
- [ ] Proposal card appears with correct fields
- [ ] Zoom 2× on proposal card — confirm all fields readable

### Scene 4 — Approval and PayPal (1:20–1:55)
- [ ] Proposal card still visible from Scene 3
- [ ] Hover over Approve button — 1-second pause
- [ ] Click Approve button once only
- [ ] Both buttons disabled immediately (do not click again)
- [ ] Wait for execution to complete
- [ ] Invoice ID visible in success message
- [ ] Open Audit Log expander at bottom
- [ ] Show proposed → approved → executed entries
- [ ] Architecture overlay slide prepared as separate image

### Scene 5 — Buyer payment (1:55–2:25)
- [ ] Switch to PayPal Sandbox Business (Seller) account tab
- [ ] Invoice appears in Invoicing dashboard — confirm it is there BEFORE recording
- [ ] Show invoice status (SENT / Awaiting Payment)
- [ ] Switch to PayPal Sandbox Personal (Buyer) account (new tab or incognito)
- [ ] Find invoice in buyer's activity/invoices
- [ ] Click Pay Now
- [ ] Complete \ payment using sandbox balance
- [ ] Show payment confirmation

### Scene 6 — Final verification (2:25–2:45)
- [ ] Return to InvoicePilot Streamlit app
- [ ] Type: "Check my invoices" or "What is the status of my invoices?"
- [ ] Agent calls list_invoices (read-only)
- [ ] Agent reports invoice status: PAID, \, amount due \
- [ ] Show the agent response clearly

### Scene 7 — Closing (2:45–3:00)
- [ ] Motion graphics only — no live recording needed
- [ ] Dark background, logo, tagline, stack line

---

## PRIVACY AND SECURITY — FRAME-BY-FRAME REVIEW

Before publishing, review every frame for:

### Must blur (Gaussian blur, minimum radius 10px)
- [ ] All sandbox email addresses (any sb-*@*.com addresses)
- [ ] PayPal account balance amounts (not relevant to demo)
- [ ] Any account profile photos
- [ ] Any full name if it's a real person (Rohit is fictional — OK to show)

### Must NOT appear on screen at any point
- [ ] .env file contents
- [ ] Browser address bar when it shows API keys or OAuth tokens
- [ ] PayPal Developer Dashboard → Client ID or Client Secret fields
- [ ] GOOGLE_API_KEY value
- [ ] PAYPAL_CLIENT_ID value
- [ ] PAYPAL_SECRET / PAYPAL_CLIENT_SECRET value
- [ ] Python terminal output showing key values
- [ ] Any config.py import output that reveals credentials

### Acceptable to show
- [ ] Invoice ID: INV2-XXXX-XXXX-XXXX-XXXX (non-sensitive)
- [ ] Invoice status: DRAFT / SENT / PAID
- [ ] Invoice amount: \.00 USD
- [ ] Audit log proposal IDs (UUID format, test data only)
- [ ] App URL: localhost:8501
- [ ] Python version, package versions
- [ ] clients.json structure (blur the actual email value)

---

## EDITING WORKFLOW

### Step 1: Assemble rough cut
1. Import all screen recordings into DaVinci Resolve
2. Arrange clips in timeline order (Scene 1–7)
3. Trim to target durations (see Script)
4. Total target: 170–180 seconds

### Step 2: Add motion graphics
- Create Scene 1 (Problem) title card
- Create Scene 2 (Intro) title card
- Create Scene 4 architecture diagram overlay
- Create Scene 7 closing card

### Step 3: Add captions
- Add lower-third captions per the script
- Font: Inter or Roboto Bold
- Use DaVinci Resolve's Fusion text tool or the Edit page title overlay

### Step 4: Add voiceover
- Record voiceover in a quiet room using a USB microphone
- Import and sync to timeline
- Normalize to –14 LUFS (use DaVinci Fairlight audio page)

### Step 5: Privacy review
- Go through the full timeline frame-by-frame
- Apply Gaussian blur to all items on the Must-Blur list
- Use DaVinci's Power Mask or a blur node in Fusion

### Step 6: Colour and polish
- Apply slight vignette to screen recording clips
- Increase contrast by 10% for readability
- Smooth out any zoom animations

### Step 7: Export
- Format: MP4 / H.264
- Resolution: 1920×1080
- Bitrate: 8–12 Mbps
- Audio: AAC 192 kbps stereo
- Upload as unlisted YouTube video first for review
- Confirm audio and video sync before publishing publicly

---

## YOUTUBE UPLOAD CHECKLIST

- [ ] Title: InvoicePilot – AI-Powered Billing Assistant | PayPal AI Hackathon Demo
- [ ] Description: include project summary, tech stack, GitHub link
- [ ] Thumbnail: clean branded image with logo and tagline
- [ ] Tags: PayPal, AI, LangChain, Gemini, Streamlit, Python, Hackathon, Invoice automation
- [ ] Visibility: Public (required for submission)
- [ ] No copyrighted music confirmed
- [ ] No third-party trademarks misused
- [ ] All materials in English
- [ ] Duration: under 3:00 confirmed

---

## TIMING GUIDE (target vs. flexible)

| Scene | Target | Minimum | Maximum |
|-------|--------|---------|---------|
| 1. Problem | 20s | 15s | 25s |
| 2. Intro | 20s | 15s | 25s |
| 3. Creation | 40s | 35s | 50s |
| 4. Approval | 35s | 30s | 40s |
| 5. Payment | 30s | 25s | 35s |
| 6. Verification | 20s | 15s | 25s |
| 7. Closing | 15s | 10s | 20s |
| **TOTAL** | **180s** | **145s** | **220s** |

If the total exceeds 3:00, trim Scene 5 (payment) first — it has the most flexibility.
If it falls under 2:30, extend Scene 3 to show the AI thinking step more clearly.
