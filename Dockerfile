# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS development

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/opt/venv/bin:$PATH"

ARG DEE_UID=1000
ARG DEE_GID=1000
RUN groupadd --gid "${DEE_GID}" dee \
    && useradd --uid "${DEE_UID}" --gid dee --create-home dee \
    && mkdir -p /app /case/originals /case/working /case/database /case/output \
    && chown -R dee:dee /app /case/working /case/database /case/output

WORKDIR /app
COPY --chown=dee:dee pyproject.toml uv.lock README.md ./
COPY --chown=dee:dee src/ ./src/
RUN python -m pip install --no-cache-dir uv==0.8.22 \
    && uv sync --locked --extra dev --python /usr/local/bin/python

USER dee
CMD ["dee", "--help"]
