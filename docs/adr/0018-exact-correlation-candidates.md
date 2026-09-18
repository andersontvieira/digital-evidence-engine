# ADR 0018 — Exact-match correlation candidate groups

Status: aceita. Entrega: Milestone 3C1.

## Decisão e limites

Um CorrelationCandidate representa um grupo de observações com igualdade técnica
exata segundo regra versionada, acompanhado por N CorrelationSupports. Não existem
arestas pairwise: N ocorrências produzem um grupo e N supports, evitando N².
Somente grupos com pelo menos dois supports são persistidos. Singletons permanecem
nas tabelas de observação, sem candidato.

Candidatos são DERIVED. Igualdade não afirma mesmo aparelho, pessoa, sessão, rede
local, assinante, residência, autoria ou ownership. Modelos são compartilháveis
por muitos aparelhos; identifiers não recebem força maior automaticamente.
Não há score, confidence, temporalidade, inferência transitiva, identidade,
Device/Network/Person/Account/Session ou graph engine.

## Contratos estáticos

Somente `exact_match.correlator` 1.0.0, com duas regras 1.0.0:

- `device.exact_namespace_value`: igualdade de fact_kind, namespace e value_raw
  TEXT exatamente como persistido. Não decodificar JSON para comparar, remover
  espaços, mudar case, hífens, underscore/vírgula ou nomes comerciais. Mesmo literal
  em namespaces diferentes permanece separado.
- `network.exact_canonical_ip`: igualdade de ip_version e ip_canonical persistidos,
  somente canonical não NULL e versão 4/6. Raw, source_role e platform não participam
  da chave. Representações raw IPv6 diferentes e plataformas diferentes podem
  compartilhar grupo. Não há nova canonicalização, reparo ou lookup de IP.

Entradas aceitas explicitamente: DeviceObservation de `device.observer` 1.0.0 e
NetworkObservation de `network.observer` 1.0.0. Outras versões/IDs não são usados
automaticamente. IPs inválidos e versões não aceitas não geram grupos. Contagens
inspected incluem todas as observações do caso; candidatos usam somente as elegíveis.
Nenhum ParsedRecord, NormalizedEvent ou arquivo bruto é lido pelo correlator.

## Digest e ordem

SHA-256 de UTF-8 do JSON compacto produzido por json_text (ensure_ascii=True,
sort_keys=True, separators=(',', ':'), allow_nan=False). Formato versionado:

```text
["exact-match-key",1,rule_id,"1.0.0",fact_kind,namespace,value_raw_TEXT]
["exact-match-key",1,rule_id,"1.0.0",ip_version,ip_canonical]
```

value_raw_TEXT entra como string JSON contendo o texto persistido, sem interpretação.
O candidate guarda somente key_digest; valores reais são consultados seguindo
support -> observation. SHA-256 determinístico não é criptografia nem anonimização;
catálogos e seus derivados continuam sendo dados de caso fora do Git.

Agrupamento usa chaves completas; digests colidentes entre grupos são recusados.
Grupos são percorridos por (kind, rule_id, key JSON) ordenados. Supports são ordenados
por (parsed_record_id, observation_ordinal, observation_id), com ordinal 0-based.
Armazenamento/memória de supports cresce linearmente; ordenação custa O(N log N).

## Schema v5 e proveniência

Somente correlation_runs, correlation_candidates e correlation_supports são
adicionados. Novos catálogos nascem v5; migração explícita v1 -> v2 -> v3 -> v4 -> v5
é transacional e aditiva, sem modificar linhas anteriores. Escritas exigem v5;
verify/manifest podem ler v2/v3/v4 sem migrar; v1 continua exigindo migração.
Backup consistente precede migração de caso existente na validação controlada.

Run guarda correlator/versão, início/fim, status, contagens e diagnóstico técnico.
Candidate guarda case/run, correlator/regra/versões, kind, digest, support_count e
created_at. Unicidade: case + correlator/versão + regra/versão + digest.

Support referencia exatamente uma observação com FK e CHECK. candidate_kind no
support, combinado com FK (candidate_id, candidate_kind), impede mistura device/network
inclusive em inserts diretos. Constraints únicas impedem ordinal ou observação
repetidos no mesmo candidate. Não há cópia de raw, IP, IDs técnicos ou modelos.

Cadeia: Candidate -> Support -> DeviceObservation/NetworkObservation -> ParsedRecord
-> SourceRecord -> ArchiveMember/EvidenceFile -> original e SHA-256. O serviço
seleciona observações do mesmo case; não abre originals/working.

## Atomicidade, idempotência e divergência

BEGIN IMMEDIATE serializa o run. Um savepoint abrange todos os candidates/supports
novos; falha reverte todos, mantendo FAILED técnico quando persistível. Dados antigos
nunca são apagados. Em erro no commit, verificar durabilidade antes de registrar
COMMIT_FAILED; run já persistido permanece intacto e exige revisão manual.

Na reexecução, comparar kind, support_count e todos os supports/ordinals esperados.
Grupo desaparecido ou reduzido a singleton também é divergência. Diferença produz
SUPPORT_SET_DIVERGENCE e rollback, sem adicionar/remover/reordenar supports antigos.
Observações futuras que ampliem um grupo existente exigem escopo explícito para
versionar regras/correlator; esta entrega não implementa atualização incremental.
Novas identidades de grupos independentes podem ser adicionadas sem mudar antigos.

CLI `dee correlate exact` imprime somente contagens; exit 1 indica falha no run,
2 erro operacional/schema. Não há exposição de raw, digest ou payload no console.
