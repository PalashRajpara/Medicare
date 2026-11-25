"""Operational tools unit and integration tests."""

import pytest

from tests.support.tools.calculator import CalculatorTool
from tests.support.tools.cloud_kb import CloudKnowledgeBaseTool
from tests.support.tools.mcp_client import RemoteMCPTool
from tests.support.tools.search import WebSearchTool
from tests.support.tools.vector_store import VectorStoreRAGTool
from tests.support.tools.weather import WeatherTool


@pytest.mark.asyncio
async def test_calculator_tool():
    calc = CalculatorTool()

    # Basic arithmetic
    res = await calc.execute(expression="2 + 2 * 10")
    assert "Result: 22" in res

    # Constant pi & sqrt
    res_pi = await calc.execute(expression="round(pi, 2)")
    assert "Result: 3.14" in res_pi

    # Safety: disallow __import__ or arbitrary code
    res_malicious = await calc.execute(expression="__import__('os').system('ls')")
    assert "Disallowed" in res_malicious or "Error" in res_malicious


@pytest.mark.asyncio
async def test_web_search_tool():
    search = WebSearchTool()
    res = await search.execute(query="Python programming language")
    assert "Search Results" in res or "Synthesizing" in res


@pytest.mark.asyncio
async def test_weather_tool():
    weather = WeatherTool()
    res = await weather.execute(location="Tokyo")
    assert "Tokyo" in res
    assert "Weather" in res


@pytest.mark.asyncio
async def test_vector_store_tool():
    rag = VectorStoreRAGTool()
    res = await rag.execute(query="What is the remote work policy?")
    assert "Remote Work Policy" in res
    assert "Relevance Score" in res


@pytest.mark.asyncio
async def test_cloud_kb_tool():
    cloud_kb = CloudKnowledgeBaseTool()
    res = await cloud_kb.execute(query="cloud disaster recovery")
    assert "Cloud Knowledge Base" in res
    assert "Confidence" in res


@pytest.mark.asyncio
async def test_mcp_client_tool():
    mcp = RemoteMCPTool()
    res = await mcp.execute(action="list_branches", repository="medicare-core")
    assert "MCP" in res
    assert "main" in res or "branches" in res
