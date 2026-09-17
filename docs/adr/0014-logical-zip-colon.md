# ADR 0014 — Dois-pontos em nomes lógicos ZIP

Status: aceita por autorização explícita do operador na Milestone 2D.

Exportações suportadas contêm `:` legítimo em nomes de membros. A regra anterior
da ADR 0010 recusava esse caractere por incompatibilidade com o filesystem Windows.
A extração existente usa exclusivamente destinos numéricos gerados em staging;
nenhum member_path é passado como destino de escrita.

"Platform-incompatible characters may exist in logical archive member names
when they are never used as materialized filesystem destinations."

A exceção autorizada limita-se a `:`. O nome lógico original é preservado no
catálogo, sem renomeação ou normalização. Paths absolutos, drives Windows no início,
UNC, backslashes, traversal, controles, Unicode não NFC, outros caracteres proibidos,
links, entradas especiais e colisões continuam recusados. Não há ADS materializado.
Hashes, tamanhos, CRC, limites, transações e destinos gerados não mudam.

O teste anterior que recusava `synthetic/filename:stream` é substituído por
verificação positiva de nome lógico, destino gerado dentro de working, hash,
tamanho, CRC e idempotência. Novos testes preservam recusas de drives, UNC e
traversal com dois-pontos. A decisão não autoriza extração futura por nome lógico;
qualquer consumidor que materialize nomes precisará de política própria explícita.
