# 0002 — Originais somente para leitura

## Status

Aceito como decisão arquitetural; implementação conforme o roadmap.

## Context

Processamento e extração não podem alterar a fonte recebida nem misturar originais com derivados.

## Decision

Tratar originais como imutáveis em /case/originals. Montar esse volume read-only no Docker; destinar extrações a /case/working, persistência a /case/database e relatórios a /case/output. Manter tudo fora do repositório.

## Consequences

Nunca alterar conteúdo, timestamps ou permissões dos originais pelo motor. Diretórios graváveis não podem sobrepor originais ou seus ancestrais. O mount protege o caminho no container, não os arquivos contra outros processos do host. Na execução nativa, checagens de caminhos e permissões ainda devem ser implementadas.
