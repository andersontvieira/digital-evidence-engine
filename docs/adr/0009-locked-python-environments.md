# 0009 — Ambiente Python com lockfile

## Status

Aceito e implementado na Milestone 1.

## Context

Intervalos no pyproject.toml não fixavam dependências transitivas. Desenvolvimento
Windows 11 e Docker/Linux precisam compartilhar uma resolução reproduzível.

## Decision

Adicionar uv.lock com versões, hashes e marcadores multiplataforma. Fixar uv em
0.8.22 e sincronizar com uv sync --locked --extra dev --python 3.12. Manter layout
src, pyproject.toml, backend setuptools (fixado em 80.9.0), pytest, Ruff e mypy.
Fixar imagem Python 3.12 por digest no Dockerfile. Não introduzir Poetry, Alembic ou
outra mudança de toolchain sem uso concreto.

## Consequences

Há uma ferramenta adicional apenas no desenvolvimento/build. SQLAlchemy e Pydantic
agora têm uso concreto; bibliotecas futuras seguem adiadas. Atualizações do lock,
backend, uv ou digest são deliberadas e devem repetir validação. Wheels são próprios
de cada plataforma; o lock não implica binários idênticos em Windows e Linux. A
baseline executada é Python 3.12; outras versões exigem validação antes de uso.
Downloads são de ferramentas; o aplicativo continua sem chamadas externas.
