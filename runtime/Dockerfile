FROM node:22-trixie-slim AS node
FROM python:3.12-slim-trixie
COPY --from=node /usr/local/ /usr/local/
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap git ripgrep curl ca-certificates poppler-utils unzip && rm -rf /var/lib/apt/lists/*
ARG CODEX_VERSION=0.163.0
RUN npm install -g @openai/codex@${CODEX_VERSION}
RUN pip install --no-cache-dir uv==0.13.4
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev && pip uninstall -y uv
ARG CLAUDE_VERSION=2.1.309
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_VERSION}
COPY runtime/antigravity-release.json /tmp/antigravity-release.json
COPY scripts/install_antigravity.py /tmp/install_antigravity.py
RUN python /tmp/install_antigravity.py /tmp/antigravity-release.json /usr/local/bin/agy \
    && rm /tmp/install_antigravity.py /tmp/antigravity-release.json
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx /root/.npm /root/.cache
RUN apt-get update && apt-get install -y --no-install-recommends libseccomp2 && rm -rf /var/lib/apt/lists/*
COPY backend/core/ ./core/
COPY backend/config/ ./config/
COPY runtime/ /app/runtime/
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
RUN chmod +x /app/backend/core/login_browser.py
COPY scripts/security/minimize-image.sh /tmp/minimize-image.sh
RUN sh /tmp/minimize-image.sh && rm /tmp/minimize-image.sh
ENV PATH=/app/backend/.venv/bin:$PATH PYTHONPATH=/app/backend:/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CODEX_HOME=/credentials
WORKDIR /app
CMD ["uvicorn", "runtime.server:app", "--host", "0.0.0.0", "--port", "8090", "--no-access-log"]
