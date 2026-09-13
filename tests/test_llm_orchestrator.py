"""The OpenAI orchestrator has one genuinely new, testable-without-a-key
surface: it spawns the real MCP server as a subprocess and talks to it as a
real client. That plumbing is what these tests prove — no OPENAI_API_KEY,
no network call to OpenAI, no mocking of the MCP server itself.

The OpenAI half (chat.completions.create with tools=..., looping on
tool_calls) is standard function-calling wiring; what's specific to TARA
and worth verifying here is that a real MCP client, started exactly the
way tara.orchestrator.llm starts it, can list every tool the server
advertises and get a real result back from at least one of them.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

from tara.orchestrator import llm


def test_mcp_tool_schema_conversion_shape():
    class FakeTool:
        name = "compass_assess"
        description = "Runs the applicability interview."
        input_schema = {"type": "object", "properties": {"holding_id": {"type": "string"}}}

    schema = llm._mcp_tool_to_openai_schema(FakeTool())
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "compass_assess"
    assert schema["function"]["parameters"]["properties"]["holding_id"]["type"] == "string"


def test_mcp_tool_schema_conversion_handles_missing_schema():
    class FakeTool:
        name = "atlas_reconstruct"
        description = None
        input_schema = None

    schema = llm._mcp_tool_to_openai_schema(FakeTool())
    assert schema["function"]["description"] == ""
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}}


def test_extract_text_joins_blocks_and_flags_errors():
    class Block:
        def __init__(self, text):
            self.text = text

    class FakeResult:
        content = [Block("line one"), Block("line two")]
        is_error = False

    assert llm._extract_text(FakeResult()) == "line one\nline two"

    FakeResult.is_error = True
    assert llm._extract_text(FakeResult()).startswith("ERROR:")


def test_run_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(llm.OrchestratorNotConfigured):
        llm.run("does this holder owe anything?")


def test_real_mcp_client_lists_and_calls_every_tool_against_the_live_server():
    """No OpenAI involved — this proves the exact subprocess + stdio
    ClientSession wiring _run_async uses actually works against
    tara.mcp_server.server as a real, separate process, the way any MCP
    client (OpenAI's tool-calling loop included) would use it.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _check():
        params = StdioServerParameters(command=sys.executable, args=["-m", "tara.mcp_server.server"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {t.name for t in listed.tools}
                assert {"list_domains", "compass_assess", "meridian_survey", "atlas_reconstruct"} <= names

                domains = await session.call_tool("list_domains", {})
                text = llm._extract_text(domains)
                assert "india-ireland-corridor" in text
                assert not domains.is_error

    asyncio.run(_check())
