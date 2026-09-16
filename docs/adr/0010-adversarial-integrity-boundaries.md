# 0010 — Integridade sob entradas adversariais e falhas operacionais

## Status

Aceito e implementado na auditoria da Milestone 1. Complementa ADRs 0007 e 0008;
não altera schema v1 nem introduz comandos ou parsers de plataformas.

## Context

Testes sintéticos reproduziram aceitação de ZIP truncado por tamanho/CRC falsificados,
sucesso de reingestão com extração apagada e colisões de diretórios implícitos.
Abrir SQLite normalmente também permitia que verify recuperasse um hot journal.
Outro limite transacional: uma exceção após commit não autoriza apagar arquivos
que o banco já pode ter referenciado duravelmente.

## Decision

- Usar zipfile para inventário e validações locais de header/overlap, mas descomprimir
  STORE/DEFLATE diretamente em blocos limitados. Medir todo o intervalo comprimido,
  exigir EOF DEFLATE, tamanho efetivo e CRC coerentes. Não confiar na truncagem de
  ZipExtFile ao tamanho declarado. Recusar trailing data dentro desse intervalo.
- Limitar leituras de metadados a 32 MiB e contar os registros reais da central
  directory antes de zipfile criar ZipInfo, sem confiar na contagem do EOCD.
- Validar colisões casefold de todos os componentes, incluindo diretórios implícitos.
  Manter recusa de nomes não NFC, trailing dots/spaces, links e paths não portáveis.
- Antes de concluir cada ingestão, conferir existência, tamanho e SHA-256 de todos
  os ArchiveMembers daquele caso. Falhar explicitamente em extração ausente/alterada;
  não rematerializar automaticamente nem substituir registros anteriores.
- Sincronizar arquivos extraídos antes do commit e diretórios no runtime POSIX.
  Após exceção, consultar o status persistido do run antes de apagar staging. Limpar
  somente se o status ainda for RUNNING; caso incerto ou comprometido preserva
  materialização e gera erro operacional para revisão manual.
- Abrir catálogo de verify/manifest em SQLite URI mode=ro e PRAGMA query_only=ON.
  Não usar immutable, que poderia ignorar estado transacional relevante. Banco
  ausente não é criado, hot journal que exige escrita provoca erro. Recusar WAL
  antes de conectar para impedir criação/mutação de arquivos de shared memory.
- Emitir manifesto como bytes UTF-8/LF também em stdout, independentemente do
  encoding e da tradução de newlines do terminal nativo.

## Consequences

Reingestão lê novamente derivados; o custo é proporcional ao volume materializado.
Catálogo e áreas graváveis precisam permanecer confiáveis e estáveis. ZIPs com
metadados acima do teto ou variantes recusadas exigem revisão, não recuperação
parcial silenciosa. Limites não impõem quota total de memória, disco ou CPU.

Filesystem e banco não são uma transação única. Crash pode deixar RUNNING e staging
órfão; incerteza após commit exige inspeção, sem limpeza automática. fsync não é
garantia de persistência física em qualquer hardware/filesystem; sincronização de
diretórios não é implementada para Windows nativo. A execução canônica é Docker/Linux.

Leituras podem atualizar atime conforme o host/mount. Preservação estrita de metadados
exige mount read-only/noatime apropriado; o motor não restaura timestamps. Verify
cobre originais, não substitui a conferência de derivados feita pela reingestão.
