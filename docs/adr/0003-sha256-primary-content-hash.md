# 0003 — SHA-256 como hash primário de conteúdo

## Status

Aceito como decisão arquitetural; implementação conforme o roadmap.

## Context

É necessário identificar conteúdo e verificar sua consistência sem depender de nomes ou paths.

## Decision

Usar SHA-256 sobre os bytes completos de cada original e, separadamente, de seus arquivos extraídos. Preservar algoritmo, digest, tamanho e vínculo com a ocorrência; usar a biblioteca padrão hashlib quando a função for implementada.

## Consequences

Hashes idênticos não eliminam ocorrências nem comprovam autoria ou autenticidade. Hash perceptual será um mecanismo separado de similaridade. Na Evidence Foundation, calcular por streaming e detectar mudanças durante leitura; ainda não há hashing executável.
