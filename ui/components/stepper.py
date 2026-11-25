"""Live multi-agent execution stepper using native st.status."""

import time
from typing import Any

from ui.config import get_app_config

STAGE_NAMES = {
    "guardrail": "Safety Guardrail",
    "router": "Supervisor Agent",
    "supervisor": "Supervisor Agent",
    "sql": "Hospital SQL Agent",
    "sql_agent": "Hospital SQL Agent",
    "policy_rag": "Policy RAG Agent",
    "policy_agent": "Policy RAG Agent",
    "writer": "Synthesizer & Writer",
    "verifier": "Grounding Verifier",
}

STAGE_ICONS = {
    "guardrail": "🛡️",
    "router": "🧭",
    "supervisor": "🧭",
    "sql": "📊",
    "sql_agent": "📊",
    "policy_rag": "📋",
    "policy_agent": "📋",
    "writer": "✍️",
    "verifier": "🔒",
}


def format_step_description(event: dict[str, Any]) -> str:
    """Format agent_status event into readable icon + text label."""
    node = event.get("node", "agent")
    status = event.get("status", "running")
    message = event.get("message", "")
    attempt = event.get("attempt")
    max_attempts = event.get("max_attempts", 3)
    rewrite = event.get("rewrite")
    max_rewrites = event.get("max_rewrites", 2)

    icon = STAGE_ICONS.get(node, "⚡")
    name = STAGE_NAMES.get(node, node.replace("_", " ").title())

    details = []
    if attempt is not None and attempt > 1:
        details.append(f"retry {attempt}/{max_attempts}")
    if rewrite is not None and rewrite > 0:
        details.append(f"rewrite {rewrite}/{max_rewrites}")

    status_tag = ""
    if status in ("blocked", "error"):
        status_tag = "🛑 Blocked"
    elif status == "fallback":
        status_tag = "⚠️ Fallback"
    elif status == "skipped":
        status_tag = "⚪ Skipped"
    elif status in ("complete", "completed", "done"):
        status_tag = "✅ Done"
    elif status in ("running", "in_progress"):
        status_tag = "⏳ In Progress"

    desc = f"{icon} **{name}**"
    if status_tag:
        desc += f" — {status_tag}"
    if details:
        desc += f" ({', '.join(details)})"
    if message:
        desc += f": {message}"
    return desc


class StepperManager:
    """Manage live agent status stepper inside Streamlit container."""

    def __init__(self, status_container: Any) -> None:
        self.status = status_container
        self.start_time = time.time()
        self.seen_events: list[str] = []

    def on_event(self, event_content: dict[str, Any]) -> None:
        """Render updated agent status event."""
        desc = format_step_description(event_content)
        self.seen_events.append(desc)
        elapsed = time.time() - self.start_time

        cfg = get_app_config()
        base_label = cfg.get("ui", {}).get("analyzing_request_label", "Analyzing request...")
        header_label = base_label
        if elapsed > 8.0:
            header_label = f"{base_label} ({elapsed:.1f}s)"

        self.status.update(label=header_label, state="running", expanded=True)
        self.status.write(desc)

    def complete(self, label: str = "Analysis complete") -> None:
        """Collapse stepper and mark complete."""
        self.status.update(label=label, state="complete", expanded=False)

    def error(self, label: str = "Execution halted") -> None:
        """Mark stepper as error state while keeping it openable."""
        self.status.update(label=label, state="error", expanded=True)
