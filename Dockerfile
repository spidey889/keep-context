FROM ghcr.io/astral-sh/uv:0.11.26 AS uv
FROM python:3.14-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable && \
    useradd --uid 10001 --create-home keepcontext && \
    mkdir /data && chown keepcontext:keepcontext /data
USER keepcontext
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8800
CMD ["keep-context-hosted", "--host", "0.0.0.0", "--state-file", "/data/hosted.enc"]
