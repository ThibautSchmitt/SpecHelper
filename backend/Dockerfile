FROM golang:1.27.3-trixie AS github-cli
ARG GH_VERSION=2.103.3
ENV GOSUMDB=sum.golang.org CGO_ENABLED=0
# Rebuild the pinned upstream release with its fixed HTML parser dependency.
RUN go mod download github.com/cli/cli/v2@v${GH_VERSION} \
    && cp -a /go/pkg/mod/github.com/cli/cli/v2@v${GH_VERSION} /src \
    && chmod -R u+w /src
WORKDIR /src
RUN --mount=type=tmpfs,target=/root/.cache/go-build \
    GOMAXPROCS=2 go mod edit -require=golang.org/x/net@v0.62.0 && GOMAXPROCS=2 go mod tidy \
    && go mod verify \
    && GOMAXPROCS=2 go build -p=2 -trimpath -ldflags="-s -w -X github.com/cli/cli/v2/internal/build.Version=${GH_VERSION}" -o /out/gh ./cmd/gh \
    && cp /go/pkg/mod/golang.org/x/net@v0.62.0/LICENSE /out/x-net-LICENSE \
    && /out/gh --version \
    && rm -rf /go/pkg/mod

FROM python:3.12-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/app/backend/.venv/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.13.4
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev && pip uninstall -y uv
COPY --from=github-cli /out/gh /usr/local/bin/gh
COPY --from=github-cli /src/LICENSE /usr/share/licenses/github-cli/LICENSE
COPY --from=github-cli /out/x-net-LICENSE /usr/share/licenses/github-cli/x-net-LICENSE
COPY scripts/security/update-libraries.sh /tmp/update-libraries.sh
RUN sh /tmp/update-libraries.sh && rm /tmp/update-libraries.sh
COPY backend/ ./
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
RUN chmod +x core/git_askpass.py core/login_browser.py
RUN groupadd --gid 10000 spechelper && useradd --uid 10000 --gid 10000 --create-home spechelper
COPY scripts/security/minimize-image.sh /tmp/minimize-image.sh
RUN sh /tmp/minimize-image.sh && rm /tmp/minimize-image.sh
USER 10000:10000
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60"]
