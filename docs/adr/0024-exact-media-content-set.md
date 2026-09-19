# ADR 0024 — Exact media content set

Status: aceita. Entrega: Milestone 5A1.

`dee media contents` projeta em memória as occurrences reconhecidas e verificadas
por inventory_media da 5A. Reutiliza integralmente descoberta, assinaturas e
verificação size/SHA-256; não introduz outro scanner nem acesso adicional aos bytes.
Schema v5, sem tabelas, runs, migrations, views, índices, cache ou novas dependências.
Os contratos read-only e erros de integridade da 5A continuam válidos. O comando
não gera arquivos nem altera originals/working; atime depende do filesystem/mount.

Cada SHA-256 catalogado distinto define um conteúdo exato, inclusive singletons.
Todas as occurrences permanecem independentes e presentes. Formato, tipo e tamanho
devem coincidir dentro de cada SHA; inconsistência causa erro técnico/exit 2, sem
JSON parcial. Não há relações pairwise nem inferência de autoria, upload ou evento.

Occurrences e representative contêm source_kind, evidence_file_id,
archive_member_id, evidence_relative_path e member_path, sem path absoluto/físico.
Ordenam por source_kind, evidence_relative_path, member_path-or-empty,
evidence_file_id, archive_member_id-or-empty, ASC. A primeira é representative:
apenas uma escolha computacional determinística, nunca uma evidência canônica,
preferência probatória ou seleção por qualidade/mtime. Conteúdos ordenam por
media_kind, media_format e content_sha256, ASC; contagens por formato/tipo contam
conteúdos SHA distintos, não occurrences. JSON determinístico sem relógio ou UUID.

A futura 5B deve preferencialmente executar decode/perceptual hash uma vez por
exact content e projetar o resultado às occurrences, preservando suas proveniências.
Esta entrega não inicia 5B: sem decode, dimensões, perceptual hash, EXIF, OCR,
thumbnails ou investigação de ISO-BMFF. Outputs reais e helpers ficam fora do Git.
