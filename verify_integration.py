import os, sys, json

results = []

def report(name, status, detail=''):
    results.append((name, status, detail))
    icon = {'PASS': '[PASS]', 'FAIL': '[FAIL]', 'BLOCKED': '[BLOCKED]'}
    print(icon.get(status, '[???]') + ' ' + name)
    if detail:
        for line in str(detail).strip().splitlines():
            print('       ' + line)
    print()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Normalize env var aliases
if not os.getenv('PAYPAL_SECRET') and os.getenv('PAYPAL_CLIENT_SECRET'):
    os.environ['PAYPAL_SECRET'] = os.getenv('PAYPAL_CLIENT_SECRET')
if not os.getenv('GEMINI_MODEL'):
    os.environ['GEMINI_MODEL'] = 'gemini-2.5-flash'

REQUIRED = ['PAYPAL_CLIENT_ID', 'PAYPAL_SECRET', 'GOOGLE_API_KEY', 'GEMINI_MODEL']

def normalize_content(resp):
    raw = resp.content if hasattr(resp, 'content') else str(resp)
    if isinstance(raw, list):
        parts = []
        for p in raw:
            if isinstance(p, str): parts.append(p)
            elif hasattr(p, 'text'): parts.append(p.text)
            else: parts.append(str(p))
        return ' '.join(parts)
    return str(raw)

def test_env():
    missing = [v for v in REQUIRED if not os.getenv(v)]
    if missing:
        report('1. Environment variables', 'BLOCKED', 'Missing: ' + ', '.join(missing))
        return False
    ph = [v for v in REQUIRED if os.getenv(v, '').startswith('your_')]
    if ph:
        report('1. Environment variables', 'BLOCKED', 'Placeholder: ' + ', '.join(ph))
        return False
    report('1. Environment variables', 'PASS', 'All present. GEMINI_MODEL=' + os.getenv('GEMINI_MODEL'))
    return True

def test_gemini():
    mn = os.getenv('GEMINI_MODEL')
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = ChatGoogleGenerativeAI(model=mn, google_api_key=os.getenv('GOOGLE_API_KEY'))
        resp = model.invoke('Reply with exactly: INVOICEPILOT_OK')
        content = normalize_content(resp)
        if 'INVOICEPILOT_OK' in content.upper():
            report('2. Gemini API connectivity', 'PASS', 'Model: ' + mn + ', response received.')
            return model
        report('2. Gemini API connectivity', 'FAIL', 'Unexpected: ' + content[:200])
        return None
    except Exception as e:
        key = os.getenv('GOOGLE_API_KEY', '')
        err = str(e).replace(key, '<REDACTED>')
        report('2. Gemini API connectivity', 'FAIL', 'Model: ' + mn + chr(10) + 'Error: ' + err[:300])
        return None

def test_gemini_tools(model):
    if model is None:
        report('3. Gemini tool-calling', 'BLOCKED', 'Depends on test 2.')
        return False
    try:
        from langchain_core.tools import tool
        from langchain.agents import create_agent
        @tool
        def get_count() -> str:
            """Returns the total number of invoices."""
            return json.dumps({'count': 42})
        agent = create_agent(model=model, tools=[get_count], system_prompt='Test assistant. Use get_count tool.')
        result = agent.invoke({'messages': [{'role': 'user', 'content': 'How many invoices?'}]})
        msgs = result.get('messages', [])
        called = any(m.__class__.__name__ == 'ToolMessage' for m in msgs)
        final = normalize_content(msgs[-1]) if msgs else ''
        if called or '42' in final:
            report('3. Gemini tool-calling', 'PASS', 'Tool called successfully.')
            return True
        report('3. Gemini tool-calling', 'FAIL', 'Tool not called. Final: ' + final[:200])
        return False
    except Exception as e:
        key = os.getenv('GOOGLE_API_KEY', '')
        err = str(e).replace(key, '<REDACTED>')
        report('3. Gemini tool-calling', 'FAIL', 'Error: ' + err[:300])
        return False

def test_paypal():
    try:
        from paypal_agent_toolkit.langchain.toolkit import PayPalToolkit
        from paypal_agent_toolkit.shared.configuration import Configuration, Context
        cfg = Configuration(actions={'invoices': {'list': True, 'get': True}}, context=Context(sandbox=True))
        tk = PayPalToolkit(client_id=os.getenv('PAYPAL_CLIENT_ID'), secret=os.getenv('PAYPAL_SECRET'), configuration=cfg)
        tools = tk.get_tools()
        names = [t.name for t in tools]
        lt = next((t for t in tools if t.name == 'list_invoices'), None)
        if lt is None:
            report('4. PayPal auth', 'FAIL', 'list_invoices not found.')
            return None
        rs = lt.invoke({})
        try:
            r = json.loads(rs) if isinstance(rs, str) else rs
        except (TypeError, ValueError):
            r = rs
        rl = str(r).lower()
        if '401' in rl or 'unauthorized' in rl:
            report('4. PayPal auth', 'FAIL', 'Auth failed (401). Check credentials.')
            return None
        report('4. PayPal auth', 'PASS', 'OK. Tools: ' + str(names))
        return tk
    except Exception as e:
        cid = os.getenv('PAYPAL_CLIENT_ID', '')
        sec = os.getenv('PAYPAL_SECRET', '')
        err = str(e).replace(cid, '<REDACTED>').replace(sec, '<REDACTED>')
        report('4. PayPal auth', 'FAIL', 'Error: ' + err[:300])
        return None

def test_toolkit_version():
    try:
        from importlib.metadata import version as pv
        v = pv('paypal-agent-toolkit')
        from paypal_agent_toolkit.langchain.toolkit import PayPalToolkit
        from paypal_agent_toolkit.shared.configuration import Configuration, Context
        rc = Configuration(actions={'invoices': {'list': True, 'get': True}}, context=Context(sandbox=True))
        rt = PayPalToolkit(client_id=os.getenv('PAYPAL_CLIENT_ID'), secret=os.getenv('PAYPAL_SECRET'), configuration=rc)
        rtools = [t.name for t in rt.get_tools()]
        wc = Configuration(actions={'invoices': {'create': True, 'sendReminder': True}}, context=Context(sandbox=True))
        wt = PayPalToolkit(client_id=os.getenv('PAYPAL_CLIENT_ID'), secret=os.getenv('PAYPAL_SECRET'), configuration=wc)
        wtools = [t.name for t in wt.get_tools()]
        ok = ('list_invoices' in rtools and 'get_invoice' in rtools and 'create_invoice' in wtools and 'send_invoice_reminder' in wtools)
        st = 'PASS' if ok else 'FAIL'
        report('5. Toolkit version and tools', st, 'v=' + v + ' read=' + str(rtools) + ' write=' + str(wtools))
        return ok
    except Exception as e:
        report('5. Toolkit version and tools', 'FAIL', 'Error: ' + str(e)[:300])
        return False

# Test 6: Do NOT call create_invoice during diagnostics (it auto-sends)
def test_invoice_creation_blocked():
    report('6. Sandbox invoice creation', 'BLOCKED', 'Skipped during diagnostics. create_invoice auto-sends; requires explicit human approval.')

print('=' * 70)
print('InvoicePilot Integration Verification (Task 0.2)')
print('=' * 70)
print()
if not test_env():
    sys.exit(2)
model = test_gemini()
test_gemini_tools(model)
tk = test_paypal()
test_toolkit_version()
test_invoice_creation_blocked()
print('=' * 70); print('SUMMARY'); print('=' * 70)
for n, s, _ in results: print('  [' + s + '] ' + n)
p = sum(1 for _, s, _ in results if s == 'PASS')
f = sum(1 for _, s, _ in results if s == 'FAIL')
b = sum(1 for _, s, _ in results if s == 'BLOCKED')
print(); print('  ' + str(p) + ' passed, ' + str(f) + ' failed, ' + str(b) + ' blocked')
print('=' * 70)
sys.exit(1 if f else (2 if b else 0))
