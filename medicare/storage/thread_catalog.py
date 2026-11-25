"""Thread catalog helper utilities and cross-tenant validation."""

import re

from medicare.domain.models import ConversationThread


def generate_thread_title(human_prompt: str, max_length: int = 60) -> str:
    """Generate a clean title from the initial human prompt truncated to max_length."""
    cleaned = re.sub(r"\s+", " ", human_prompt.strip())
    if len(cleaned) <= max_length:
        return cleaned or "New Conversation"
    return cleaned[:max_length].rstrip() + "..."


def sanitize_thread_list(
    threads: list[ConversationThread], requesting_user_id: str, agent_id: str | None = None
) -> list[ConversationThread]:
    """Ensure strict tenant isolation by filtering threads matching user_id and agent_id."""
    return [
        t
        for t in threads
        if t.user_id == requesting_user_id and (agent_id is None or t.agent_id == agent_id)
    ]
