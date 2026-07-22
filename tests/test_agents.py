"""Every sidebar agent must have a system prompt and complete definition."""
from core.agents import AGENTS, get_agent

SIDEBAR_KEYS = [
    "general", "website", "code", "automation",
    "writer", "researcher", "designer", "maps_prospector", "manager",
]


def test_all_sidebar_agents_defined():
    for key in SIDEBAR_KEYS:
        assert key in AGENTS, f"missing agent definition: {key}"


def test_agent_definitions_complete():
    for key in SIDEBAR_KEYS:
        agent = get_agent(key)
        assert agent.name, key
        assert agent.system_prompt and len(agent.system_prompt) > 20, key
        assert agent.id == key


def test_get_agent_unknown_falls_back():
    agent = get_agent("nonexistent-agent-xyz")
    assert agent is not None
