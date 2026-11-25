"""Remote Model Context Protocol (MCP) tool client over HTTP."""

from typing import Any

import httpx

from medicare.config import settings
from medicare.tools.base import BaseTool


class RemoteMCPTool(BaseTool):
    """Tool that interacts with remote MCP servers for repository workflows."""

    name = "mcp_repository_tool"
    description = "Interact with remote repositories to list commits, browse code, or check pull requests via Model Context Protocol."

    def __init__(self, endpoint: str | None = None, token: str | None = None) -> None:
        self.endpoint = endpoint or settings.REMOTE_MCP_URL
        self.token = token or settings.REMOTE_MCP_TOKEN

    async def execute(
        self, action: str = "list_branches", repository: str = "medicare-core", **kwargs: Any
    ) -> str:
        if not self.endpoint:
            # Graceful zero-tool / mock fallback if unconfigured
            return (
                f"[MCP Client] Notice: REMOTE_MCP_URL not configured. "
                f"Simulating '{action}' for repo '{repository}': main, staging, feature/multi-agent."
            )

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    f"{self.endpoint}/tools/{action}",
                    json={"repository": repository, **kwargs},
                    headers=headers,
                )
                if resp.status_code == 200:
                    return f"[MCP Response] {resp.text}"
                return f"[MCP Client Error] Remote server returned HTTP {resp.status_code}: {resp.text}"
        except Exception as err:
            return f"[MCP Client Connection Error] {err}"
