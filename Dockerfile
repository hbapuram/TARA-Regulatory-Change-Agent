# Standalone TARA MCP server — the exact same 10 tools tara/mcp_server/server.py
# exposes locally over stdio, run instead over streamable-HTTP so it can be
# deployed and called from anywhere. See deploy/README.md for platform steps.
#
# Build:  docker build -t tara-mcp .
# Run:    docker run -p 8000:8000 -e PORT=8000 tara-mcp
# Test:   curl -i -X POST http://localhost:8000/mcp \
#           -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
#           -d '{"jsonrpc":"2.0","id":1,"method":"initialize", ...}'   # a real MCP client is simpler — see deploy/README.md
FROM python:3.11-slim

WORKDIR /app

# Only the non-dev, non-llm dependencies are needed to serve tools — the
# orchestrator's OpenAI client and pytest never run inside this container.
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY tara/ tara/
COPY domains/ domains/
COPY registers/ registers/
COPY data/ data/
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --no-deps -e .

# Render/Railway/Fly.io all inject PORT at runtime; server.py reads it
# directly (see tara/mcp_server/server.py::main), so no extra env wiring is
# needed beyond exposing the port here for local `docker run` convenience.
EXPOSE 8000

CMD ["python", "-m", "tara.cli", "serve", "--transport", "streamable-http"]
