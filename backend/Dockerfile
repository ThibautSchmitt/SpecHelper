FROM python:3.12-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/app/backend/.venv/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.13.4
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev && pip uninstall -y uv
ARG GH_VERSION=2.103.0
# Official signed repository; fail if the documented trust key changes unexpectedly.
RUN python -c 'import hashlib,pathlib,urllib.request; data=urllib.request.urlopen("https://cli.github.com/packages/githubcli-archive-keyring.gpg",timeout=60).read(); assert hashlib.sha256(data).hexdigest()=="6084d5d7bd8e288441e0e94fc6275570895da18e6751f70f057485dc2d1a811b"; root=pathlib.Path("/etc/apt/keyrings"); root.mkdir(parents=True,exist_ok=True); (root/"githubcli-archive-keyring.gpg").write_bytes(data)'
RUN echo 'deb [signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main' > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh=${GH_VERSION} && rm -rf /var/lib/apt/lists/*
COPY backend/ ./
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
RUN chmod +x core/git_askpass.py core/login_browser.py
RUN groupadd --gid 10000 spechelper && useradd --uid 10000 --gid 10000 --create-home spechelper
COPY scripts/security/minimize-image.sh /tmp/minimize-image.sh
RUN sh /tmp/minimize-image.sh && rm /tmp/minimize-image.sh
USER 10000:10000
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60"]
