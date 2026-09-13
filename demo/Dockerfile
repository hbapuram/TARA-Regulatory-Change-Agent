# The public demo: the TARA agent pipeline behind a browser-callable JSON API,
# serving the wizard page from the same origin.
#
# This is a sibling of the repo-root Dockerfile, not a replacement. That one
# serves MCP over streamable-HTTP for real MCP clients; this one serves the
# demo. They share every agent and every domain pack.
#
# Build:  docker build -f demo/Dockerfile -t tara-demo .
# Run:    docker run -p 8000:8000 tara-demo   →   http://localhost:8000
FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml requirements.txt README.md ./
COPY demo/requirements.txt demo/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r demo/requirements.txt

COPY tara/ tara/
COPY domains/ domains/
COPY registers/ registers/
COPY data/ data/
COPY demo/ demo/
COPY docs/tara-project-guide.html docs/evaluation-card.md docs/judge-slide-checklist.md docs/
RUN pip install --no-cache-dir --no-deps -e .

EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn demo.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
