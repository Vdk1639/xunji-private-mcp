FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /usr/local/bin/uv
WORKDIR /app

ENV UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
COPY src/xunji_private_mcp/ ./src/xunji_private_mcp/
RUN uv sync --locked --no-dev --no-editable

USER 10001:10001
EXPOSE 8765
ENTRYPOINT ["xunji-private-mcp"]
CMD ["http", "--host", "0.0.0.0"]
