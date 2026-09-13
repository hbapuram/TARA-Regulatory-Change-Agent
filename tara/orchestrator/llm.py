"""The OpenAI orchestrator — Phase 2.

Two different models, two different jobs: Claude (via Cowork) writes this
repo; OpenAI, at run time, is the orchestrator that connects to the MCP
server as a real client, chooses which tool to call, and explains the
result in natural language. It never computes a date, a diff or a
threshold itself — every number it reports came from a tool call, and
every finding it states carries the provision that tool returned.

This is a genuine MCP client, not a shortcut into the agents: it spawns
``python -m tara.mcp_server.server`` as a subprocess over stdio, exactly as
any other MCP client would, and only ever reaches TARA's agents through the
tool calls that server exposes. ``tara.orchestrator.direct.run_demo`` is
what keeps working if OPENAI_API_KEY isn't set, or if a live demo needs a
deterministic fallback.

Non-negotiable prompt rules (enforced in SYSTEM_PROMPT below, not just
documented here):
  - Never compute a date, difference or threshold — always call the tool.
  - Never state a finding without the provision the tool returned.
  - If applicability cannot be resolved, return INDETERMINATE and stop.
  - Follow band order — never reach PLOT before COMPASS has confirmed.
  - Report obligations only — never suggest buying, selling or holding.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SYSTEM_PROMPT = """You are the orchestrator for TARA (Tax, Assets & Residency Advisor), a \
cross-border compliance query tool. You have no knowledge of tax law, dates, or thresholds \
of your own — everything you say must come from a tool call to the TARA MCP server.

Rules you must never break:
1. Never compute a date, a difference, a threshold, or any numeric result yourself. If you \
need one, call a tool — do not estimate, round, or reason it out in prose.
2. Never state a finding, obligation, or deadline without the provision (e.g. "Section 4.2") \
the tool call returned it under. If a tool result has no provision, say so rather than \
inventing one.
3. Respect band order: for a given holding, call compass_assess (directly, or implicitly via \
plot_align/course_plan/anchor_verify, which run it internally) before treating anything about \
that holding as CONFIRMED. Never report actions or evidence outcomes for a holding you have \
not established is CONFIRMED this conversation.
4. If a tool returns INDETERMINATE with a missing_question, ask the user for that one fact \
and stop — do not guess it or assume a default.
 5. For a holder who may carry more than one citizenship or tax residency, prefer \
    meridian_survey over calling each domain's tools one at a time, so a cross-jurisdiction \
    obligation (one that exists only because two facts are true at once) is not missed.
7. Before calling survey_detect_change or legend_decompose, call list_domains and then \
   list_sources for the relevant domain. Use only the exact source_id returned by list_sources; \
   never invent a source_id from a human description of a holding or jurisdiction.
8. Before calling compass_assess, plot_align, course_plan, anchor_verify, or meridian_survey, \
   call list_holdings and use only the exact holding_id returned there; never invent one from a name.
9. TARA reports compliance obligations only. Never suggest buying, selling, holding, or \
otherwise acting on an asset — that is explicitly out of scope, even if asked directly. \
Redirect to what the person is required to do, not what they should do with their money.
7. Cite domain_id and obligation_id alongside every finding so the person can trace it back \
to a specific source (call list_domains if you need to know what's linked).

Be concise. Do not narrate which tool you are about to call — just call it, then report what \
it returned."""


class OrchestratorNotConfigured(RuntimeError):
    pass


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "arguments": self.arguments, "result": self.result}


@dataclass
class OrchestratorResult:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"answer": self.answer, "tool_calls": [t.as_dict() for t in self.tool_calls]}


def _mcp_tool_to_openai_schema(tool: Any) -> dict[str, Any]:
    """Converts one MCP Tool (as returned by session.list_tools()) into an
    OpenAI function-calling tool schema. This is the only place that
    translates between the two protocols — the MCP server's tool
    definitions (tara/mcp_server/server.py) are the single source of truth
    for what the model can do; nothing about a tool's shape is duplicated
    here.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema or {"type": "object", "properties": {}},
        },
    }


def _extract_text(result: Any) -> str:
    """CallToolResult.content is a list of content blocks (usually
    TextContent, since every TARA tool returns a JSON-serializable dict) —
    join whatever text is there rather than assuming exactly one block.
    """
    parts = [block.text for block in result.content if hasattr(block, "text")]
    text = "\n".join(parts) if parts else str(result)
    if getattr(result, "is_error", False):
        return f"ERROR: {text}"
    return text


async def _run_async(
    prompt: str,
    model: str,
    max_turns: int,
    server_command: list[str] | None = None,
) -> OrchestratorResult:
    from openai import AsyncOpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise OrchestratorNotConfigured(
            "OPENAI_API_KEY is not set. Use `python -m tara.cli demo --direct` instead, "
            "which runs the identical pipeline with no model in the loop."
        )

    client = AsyncOpenAI(api_key=api_key)

    command, *args = server_command or [sys.executable, "-m", "tara.mcp_server.server"]
    server_params = StdioServerParameters(command=command, args=args)

    tool_calls: list[ToolCallRecord] = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            openai_tools = [_mcp_tool_to_openai_schema(t) for t in listed.tools]

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            for _ in range(max_turns):
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto",
                )
                choice = response.choices[0]
                assistant_message = choice.message
                messages.append(assistant_message.model_dump(exclude_none=True))

                if not assistant_message.tool_calls:
                    return OrchestratorResult(answer=assistant_message.content or "", tool_calls=tool_calls)

                for call in assistant_message.tool_calls:
                    try:
                        raw_args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError as exc:
                        content = f"ERROR: model produced invalid JSON arguments: {exc}"
                        raw_args = {}
                    else:
                        try:
                            tool_result = await session.call_tool(call.function.name, raw_args)
                            content = _extract_text(tool_result)
                        except Exception as exc:  # surfaced to the model, never swallowed
                            content = f"ERROR calling {call.function.name}: {exc}"

                    tool_calls.append(ToolCallRecord(name=call.function.name, arguments=raw_args, result=content))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": content,
                    })

            return OrchestratorResult(
                answer=(
                    f"(stopped after {max_turns} tool-call rounds without a final answer — "
                    "raise max_turns or narrow the query)"
                ),
                tool_calls=tool_calls,
            )


def run(
    prompt: str,
    model: str = "gpt-4.1-mini",
    max_turns: int = 8,
    server_command: list[str] | None = None,
) -> OrchestratorResult:
    """Synchronous entry point. Spawns the MCP server as a subprocess,
    connects as a client over stdio, and loops OpenAI tool calls until the
    model produces a final, non-tool-call answer (or ``max_turns`` rounds
    are exhausted, in which case the caller gets back whatever tool calls
    did happen — never silently empty).

    ``server_command`` lets a caller point at a different server invocation
    (e.g. a different Python interpreter) for testing; defaults to the same
    ``python -m tara.mcp_server.server`` any other MCP client would use.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise OrchestratorNotConfigured(
            "OPENAI_API_KEY is not set. Use `python -m tara.cli demo --direct` instead, "
            "which runs the identical pipeline with no model in the loop."
        )
    return asyncio.run(_run_async(prompt, model, max_turns, server_command))
