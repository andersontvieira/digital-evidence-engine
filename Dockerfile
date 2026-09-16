# syntax=docker/dockerfile:1
FROM python:3.12-slim AS development

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

ARG DEE_UID=1000
ARG DEE_GID=1000
RUN groupadd --gid "${DEE_GID}" dee \
    && useradd --uid "${DEE_UID}" --gid dee --create-home dee \
    && mkdir -p /app /case/originals /case/working /case/database /case/output \
    && chown -R dee:dee /app /case/working /case/database /case/output

WORKDIR /app
COPY --chown=dee:dee pyproject.toml README.md ./
COPY --chown=dee:dee src/ ./src/
RUN python -m pip install --no-cache-dir -e '.[dev]'

USER dee
CMD ["dee", "--help"]
