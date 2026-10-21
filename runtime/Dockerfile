FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm
COPY --from=node /usr/local/ /usr/local/
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap git ripgrep curl ca-certificates poppler-utils unzip && rm -rf /var/lib/apt/lists/*
ARG CODEX_VERSION=0.163.0
RUN npm install -g @openai/codex@${CODEX_VERSION}
RUN pip install --no-cache-dir uv==0.8.14
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
ARG CLAUDE_VERSION=2.1.116
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_VERSION}
COPY backend/core/ ./core/
COPY backend/config/ ./config/
COPY runtime/ /app/runtime/
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
RUN chmod +x /app/backend/core/login_browser.py
ENV PATH=/app/backend/.venv/bin:$PATH PYTHONPATH=/app/backend:/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CODEX_HOME=/credentials
WORKDIR /app
CMD ["uvicorn", "runtime.server:app", "--host", "0.0.0.0", "--port", "8090", "--no-access-log"]
