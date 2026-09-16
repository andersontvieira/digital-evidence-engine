# 0008 — ZIP conservador de primeiro nível

## Status

Aceito e implementado na Milestone 1. Complementado pela ADR 0010 após auditoria.

## Context

Containers são entradas não confiáveis: nomes, tamanhos declarados, links,
duplicatas e razão de compressão podem causar fuga de paths ou exaustão de recursos.

## Decision

Validar todo o inventário antes de escrever. Recusar traversal, caminhos absolutos,
Windows/backslashes, nomes inválidos/não portáveis/não NFC, links, arquivos especiais,
duplicatas inclusive por casefold e conflitos arquivo/diretório. Decoding segue
UTF-8/CP437 do ZIP; não tentar consertar nomes silenciosamente.

Extrair membro a membro, sem extractall, em diretório exclusivo da execução sob
working, usando nomes gerados numericamente e abertura exclusiva. Preservar nomes
originais e relação com container no banco. Permitir somente STORE/DEFLATE sem
criptografia. Validar CRC/tamanho e impor limites declarados e reais: 512 MiB por
arquivo, 2 GiB por ZIP, 10000 entradas e razão 200; todos configuráveis e auditados.

Não extrair ZIPs dentro de ZIPs. Catalogá-los como membros opacos com hash próprio.

## Consequences

Alguns ZIPs legítimos são recusados deliberadamente. Nomes extraídos não reproduzem
a árvore original; o banco/manifesto preserva essa relação. Diretórios vazios são
validados, mas não geram entidades de arquivo. Limites são por ZIP, sem quota global
de disco ou timeout. A ADR 0010 limita metadados e conta entradas antes da alocação
de objetos; esses limites não são uma quota total de memória do parser. Não há garantia contra
modificação hostil concorrente do filesystem; isolamento e originais estáveis são
responsabilidade operacional. A segurança tem precedência sobre recuperar entradas
parcialmente válidas de um container recusado.
