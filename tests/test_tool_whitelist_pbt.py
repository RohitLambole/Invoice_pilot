"""Property-based test for the tool whitelist conformance invariant (Task 6.2).

**Validates: Requirements 5.1, 5.5, 5.6**

Property 3: Tool_whitelist conformance
For ALL agent tool-call traces, no NEVER_EXPOSED_Tool appears in the set of
tools the agent invokes, and every tool the agent holds is in the allowed set.

This is a static configuration check against the registered tool set. The
``conftest.py`` stubs the PayPal toolkit (so ``get_tools()`` returns ``[]``)
and ``config`` so that importing :mod:`agent` is hermetic.
"""

from hypothesis import given, settings, strategies as st

import agent


@given(st.sampled_from(agent.NEVER_EXPOSED_TOOL_NAMES))
@settings(deadline=None)
def test_no_never_exposed_tool_in_agent_tools(name):
    """No tool whose name is in NEVER_EXPOSED_TOOL_NAMES is registered with
    the agent — the agent can never escalate to a write/destructive PayPal op.

    **Validates: Requirements 5.1, 5.5, 5.6**
    """
    all_names = [t.name for t in agent.all_tools]
    assert name not in all_names, (
        f"NEVER_EXPOSED tool '{name}' found in agent all_tools: {all_names}"
    )


@given(st.sampled_from([t.name for t in agent.all_tools]))
@settings(deadline=None)
def test_every_agent_tool_is_in_allowed_set(name):
    """Every tool registered with the agent is in the allowed whitelist
    (read-only PayPal tools + custom proposal tools).

    **Validates: Requirements 5.1, 5.5, 5.6**
    """
    allowed = set(agent.EXPECTED_READ_TOOL_NAMES) | set(
        agent.EXPECTED_PROPOSAL_TOOL_NAMES
    )
    assert name in allowed, (
        f"Unexpected tool '{name}' registered (not in allowed set {allowed})"
    )


def test_all_tools_disjoint_from_never_exposed():
    """Belt-and-suspenders: the full tool set and the never-exposed set share
    no name, and the union of allowed names covers all registered tools.
    """
    all_names = {t.name for t in agent.all_tools}
    never = set(agent.NEVER_EXPOSED_TOOL_NAMES)
    assert all_names.isdisjoint(never)

    allowed = set(agent.EXPECTED_READ_TOOL_NAMES) | set(
        agent.EXPECTED_PROPOSAL_TOOL_NAMES
    )
    assert all_names <= allowed
