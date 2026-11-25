"""Dynamic registry of MediCare Multi-Agent System."""

from medicare.agents.base import BaseAgent
from medicare.agents.hospital_sql_agent import HospitalSQLAgent
from medicare.agents.medicare_navigator import MediCareNavigatorAgent
from medicare.agents.policy_rag_agent import PolicyRAGAgent
from medicare.config import settings
from medicare.domain.errors import AgentNotFoundError
from medicare.domain.models import AgentInfo


class AgentRegistry:
    """Manages discovery and lifecycle of all registered agents."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._register_default_catalog()

    def _register_default_catalog(self) -> None:
        catalog: list[BaseAgent] = [
            MediCareNavigatorAgent(),
            HospitalSQLAgent(),
            PolicyRAGAgent(),
        ]
        for agent in catalog:
            self._agents[agent.key] = agent

    def get_agent(self, key: str | None = None) -> BaseAgent:
        target_key = key or settings.DEFAULT_AGENT
        agent = self._agents.get(target_key)
        if not agent:
            raise AgentNotFoundError(target_key)
        return agent

    def list_agents(self) -> list[AgentInfo]:
        return [
            AgentInfo(key=agent.key, description=agent.description)
            for agent in self._agents.values()
        ]


registry = AgentRegistry()
