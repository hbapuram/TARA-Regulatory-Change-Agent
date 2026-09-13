"""Entrypoint.

    python -m tara.cli demo --direct           # deterministic pipeline, no model, no MCP
    python -m tara.cli serve                   # run the MCP server (stdio transport)
    python -m tara.cli orchestrate "<prompt>"   # OpenAI orchestrator, live over MCP (needs OPENAI_API_KEY)
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tara")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser("demo", help="Run the deterministic pipeline end to end.")
    demo_parser.add_argument(
        "--direct", action="store_true", default=True,
        help="Bypass the MCP server and the LLM orchestrator (Phase 1 default; also the demo-day fallback).",
    )

    serve_parser = subparsers.add_parser(
        "serve", help="Run the MCP server. stdio by default (local subprocess use); "
        "--transport streamable-http for a standalone, network-reachable service.",
    )
    serve_parser.add_argument(
        "--transport", choices=["stdio", "sse", "streamable-http"], default=None,
        help="Defaults to stdio, or $TARA_MCP_TRANSPORT if set. Use streamable-http to serve over HTTP (deploy/README.md).",
    )
    serve_parser.add_argument("--host", default=None, help="Bind address for streamable-http/sse (default 0.0.0.0).")
    serve_parser.add_argument("--port", type=int, default=None, help="Bind port for streamable-http/sse (default $PORT or 8000).")

    orchestrate_parser = subparsers.add_parser(
        "orchestrate",
        help="Ask a question through the OpenAI-over-MCP orchestrator (needs OPENAI_API_KEY).",
    )
    orchestrate_parser.add_argument("prompt", help="The question to ask, e.g. 'What does HLD-001 owe and by when?'")
    orchestrate_parser.add_argument("--model", default="gpt-4.1-mini", help="OpenAI model to use (default: gpt-4.1-mini).")
    orchestrate_parser.add_argument("--max-turns", type=int, default=8, help="Max tool-call rounds before giving up.")
    orchestrate_parser.add_argument(
        "--show-tool-calls", action="store_true",
        help="Print every tool call and its raw result, not just the final answer.",
    )

    args = parser.parse_args(argv)

    if args.command == "demo":
        from .orchestrator.direct import run_demo
        run_demo()
        return 0

    if args.command == "serve":
        from .mcp_server.server import main as serve_main
        # Built explicitly, not passed straight through — sys.argv at this
        # point is still ['tara', 'serve', ...], which server.py's own
        # argparse (prog="tara-mcp-server") would choke on if handed
        # unfiltered. None of these three flags were given a default above
        # (they default to None), so an omitted flag is simply absent here
        # and server.py's own env-var/stdio fallback applies unchanged.
        serve_argv: list[str] = []
        if args.transport is not None:
            serve_argv += ["--transport", args.transport]
        if args.host is not None:
            serve_argv += ["--host", args.host]
        if args.port is not None:
            serve_argv += ["--port", str(args.port)]
        serve_main(serve_argv)
        return 0

    if args.command == "orchestrate":
        try:
            from dotenv import load_dotenv
            load_dotenv()  # picks up OPENAI_API_KEY from a local .env if present; a no-op if there isn't one
        except ImportError:
            pass  # python-dotenv is an `llm` extra, not a hard dependency — OPENAI_API_KEY can still be set directly

        from .orchestrator.llm import OrchestratorNotConfigured, run as orchestrate_run

        try:
            result = orchestrate_run(args.prompt, model=args.model, max_turns=args.max_turns)
        except OrchestratorNotConfigured as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001 — this is the CLI's top-level error boundary
            # Deliberately broad: a bad API key, no network, or the model
            # producing something the MCP server rejects should all print
            # one clean line here rather than an asyncio/anyio traceback.
            # anyio's task groups wrap the real failure in an ExceptionGroup
            # — unwrap to the first leaf exception so the printed message is
            # the actual cause (e.g. an OpenAI auth or connection error),
            # not "unhandled errors in a TaskGroup".
            # getattr, not isinstance(leaf, BaseExceptionGroup): that name
            # only exists on Python 3.11+, but pyproject.toml declares
            # requires-python = ">=3.10" — an isinstance check here would
            # raise NameError on 3.10, inside the very handler meant to
            # produce a clean error message.
            leaf = exc
            while getattr(leaf, "exceptions", None):
                leaf = leaf.exceptions[0]
            print(f"error: orchestrator failed — {leaf.__class__.__name__}: {leaf}", file=sys.stderr)
            print("If this is a connectivity or auth error, `tara demo --direct` runs the same "
                  "pipeline with no model or network call.", file=sys.stderr)
            return 1

        if args.show_tool_calls:
            for call in result.tool_calls:
                print(f"--- tool: {call.name}({call.arguments}) ---")
                print(call.result)
                print()

        print(result.answer)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
