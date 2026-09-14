# The isolated agentic demo: a visible live investigator behind a
# browser-callable JSON API, serving the copied wizard page from the same origin.
#
# This is a sibling of the repo-root Dockerfile, not a replacement. That one
# serves MCP over streamable-HTTP for real MCP clients; this one serves the
# demo. They share every agent and every domain pack.
#
# Build:  docker build -f agentic_demo/Dockerfile -t tara-agentic-demo .
# Run:    docker run -p 8001:8000 tara-agentic-demo   →   http://localhost:8001
FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml requirements.txt README.md ./
COPY agentic_demo/requirements.txt agentic_demo/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r agentic_demo/requirements.txt

COPY tara/ tara/
COPY domains/ domains/
COPY registers/ registers/
COPY data/ data/
COPY agentic_demo/ agentic_demo/
RUN pip install --no-cache-dir --no-deps -e .

EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn agentic_demo.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
