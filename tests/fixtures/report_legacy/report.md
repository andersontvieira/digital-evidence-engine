# Relatório Técnico Consolidado de Análise e Organização de Evidências Digitais

## 1. Identificação do documento

Policy do relatório: report.consolidated / 1.0.0. Projeção DERIVED.

Snapshot: report.data_snapshot / 1.0.0. Evidence schema: v5. Engine: 0.1.0.

## 2. Objetivo e escopo

Consolidação de um anchor sem janela e 2 janela(s) técnica(s) fornecida(s) pelo operador. A seleção inclui todos os candidates dos prefixos retornados. Duplicatas case-wide são apresentadas uma vez, pelo anchor. Nenhuma nova análise de evidência é executada.

## 3. Natureza e limitações do trabalho

Documento técnico de organização e rastreabilidade, sem certificação pericial. ParsedRecord permanece OBSERVED; NormalizedEvent e achados automáticos permanecem DERIVED. Não são gerados achados REPORTED ou HYPOTHESIS. A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica.

## 4. Materiais/evidências analisados

Materiais representados nos snapshots; esta execução lê somente os JSONs fornecidos.

| Tabela catalogada | Linhas físicas |
| --- | --- |
| cases | 1 |
| evidence\_files | 3 |
| archive\_members | 0 |
| source\_records | 8 |
| parsed\_records | 5 |
| ingestion\_runs | 2 |
| parser\_runs | 1 |
| normalization\_runs | 3 |
| normalized\_events | 5 |
| observation\_runs | 2 |
| device\_observations | 5 |
| network\_observations | 5 |
| correlation\_runs | 2 |
| correlation\_candidates | 2 |
| correlation\_supports | 6 |

## 5. Metodologia técnica

Policies declaradas nos snapshots; disponibilidade não implica execução de componente sem janela. A 8A2 valida e projeta esses resultados, sem recalcular normalização, pares ou memberships.

| Policy/componente | Versão |
| --- | --- |
| current\_event\_policy | 1.0.0 |
| meta.event\_normalizer | 1.0.0 |
| google.event\_normalizer | 1.1.0 |
| apple.event\_normalizer | 1.0.0 |
| device.observer | 1.0.0 |
| network.observer | 1.0.0 |
| device.exact\_namespace\_value | 1.0.0 |
| network.exact\_canonical\_ip | 1.0.0 |
| exact\_match.correlator | 1.0.0 |
| temporal.proximity | 1.0.0 |
| temporal\_exact\_overlap | 1.0.0 |

## 6. Preservação, integridade e provenance

O motor possui mecanismos de SHA-256 e verificação contra baseline catalogada. Este relatório não executa verify nem afirma um resultado de verify ausente do snapshot. Não estabelece autenticidade anterior à aquisição.

Os componentes DB da 8A1 compartilham um read snapshot; mídia utiliza leituras verificadas separadas. Não há atomicidade DB/filesystem. Cada F-ID aponta para uma posição estruturada de snapshot no apêndice. O snapshot preserva IDs, locators e hashes para drill-down até o catálogo e a fonte; este relatório não replica seus valores. Snapshots e relatórios reais permanecem fora do Git.

## 7. Fontes e cobertura de parsing

Histórico de execuções de parser, sem alegação de cobertura completa da realidade.

| parser_id | parser_version | status | Linhas físicas |
| --- | --- | --- | --- |
| meta.profile\_activity | 1.1.0 | COMPLETED | 1 |

## 8. Normalização temporal

Linhas físicas de normalized_events: 5. Current events sob current_event_policy / 1.0.0: 5. Current events datados: 5; current events sem UTC suficiente: 0. As unidades físicas e current são distintas; versões históricas não se tornam atuais pela recência.

| Plataforma | Event kind | Current events | Current datados | Current sem UTC |
| --- | --- | --- | --- | --- |
| meta | account.profile\_activity | 5 | 5 | 0 |

| normalizer_id | normalizer_version | status | Linhas físicas |
| --- | --- | --- | --- |
| apple.event\_normalizer | 1.0.0 | COMPLETED | 1 |
| google.event\_normalizer | 1.1.0 | COMPLETED | 1 |
| meta.event\_normalizer | 1.0.0 | COMPLETED | 1 |

## 9. Observações técnicas de dispositivo

Observações técnicas de dispositivo catalogadas; não representam resolução de entidade física.

| observer_id | observer_version | platform | Linhas físicas |
| --- | --- | --- | --- |
| device.observer | 1.0.0 | meta | 5 |

## 10. Observações técnicas de rede

Observações técnicas de rede catalogadas; nenhuma atribuição de pessoa ou localização é produzida.

| observer_id | observer_version | platform | Linhas físicas |
| --- | --- | --- | --- |
| network.observer | 1.0.0 | meta | 5 |

## 11. Candidates por igualdade exata

Candidates persistidos elegíveis: 2; device: 1; network: 1. Supports elegíveis: 6 linhas persistidas de suporte. Contagens de suporte não medem força probatória.

| correlator_id | correlator_version | rule_id | rule_version | candidate_kind | Linhas físicas |
| --- | --- | --- | --- | --- | --- |
| exact\_match.correlator | 1.0.0 | device.exact\_namespace\_value | 1.0.0 | device | 1 |
| exact\_match.correlator | 1.0.0 | network.exact\_canonical\_ip | 1.0.0 | network | 1 |

## 12. Timeline e janelas relevantes

### W-001

UTC [2026-01-01T00:00:00.000000Z, 2026-01-01T00:01:00.000000Z); platform=sem filtro; event-kind=sem filtro; limite de consulta=10 segundos. Current events elegíveis datados: 5; current events sem UTC sob os filtros: 0.

| Componente | Unidade | total | returned | truncated |
| --- | --- | --- | --- | --- |
| incident\_window | current\_events | 5 | 5 | false |
| incident\_candidates | persisted\_candidates | 2 | 2 | false |
| temporal\_proximity | temporal\_pairs | 10 | 10 | false |
| temporal\_exact\_overlap | temporal\_pairs | 10 | 10 | false |

### W-002

UTC [2026-01-01T00:00:00.000000Z, 2026-01-01T00:01:00.000000Z); platform=meta; event-kind=sem filtro; limite de consulta=1 segundos. Current events elegíveis datados: 5; current events sem UTC sob os filtros: 0.

| Componente | Unidade | total | returned | truncated |
| --- | --- | --- | --- | --- |
| incident\_window | current\_events | 5 | 5 | false |
| incident\_candidates | persisted\_candidates | 2 | 2 | false |
| temporal\_proximity | temporal\_pairs | 4 | 4 | false |
| temporal\_exact\_overlap | temporal\_pairs | 4 | 4 | false |

## 13. Temporal Proximity Candidates

O raio é limite de consulta. Delta menor não indica maior força. Proximidade temporal não demonstra causalidade, sessão, pessoa ou dispositivo.

| Janela | matched_pairs | returned_pairs | truncated |
| --- | --- | --- | --- |
| W-001 | 10 | 10 | false |
| W-002 | 4 | 4 | false |

## 14. Temporal + Exact Signal Overlap

Distribuição técnica exclusivamente do PREFIXO de pares retornados. Device e network permanecem separados; as contagens incluem interseção e não devem ser somadas como suportes independentes.

| Janela | matched_pairs | returned_pairs | truncated | Device | Network | Ambos | Nenhum |
| --- | --- | --- | --- | --- | --- | --- | --- |
| W-001 | 10 | 10 | false | 3 | 3 | 1 | 5 |
| W-002 | 4 | 4 | false | 2 | 2 | 1 | 1 |

## 15. Análise técnica de mídia

Igualdade de conteúdo não identifica upload, envio ou origem histórica. pHash: image.phash / 1.0.0; SUCCESS: 1; FAILED: 0; UNSUPPORTED: 0 conteúdos exatos. Nenhum valor perceptual ou comparação de similaridade é publicado.

| Medida | Contagem | Unidade |
| --- | --- | --- |
| scanned\_occurrences | 3 | ocorrências catalogadas |
| recognized\_media | 2 | ocorrências catalogadas |
| verified\_media | 2 | ocorrências catalogadas |
| unrecognized\_occurrences | 1 | ocorrências catalogadas |
| exact\_content\_count | 1 | conteúdos exatos |
| singleton\_content\_count | 0 | conteúdos exatos |
| duplicate\_content\_count | 1 | conteúdos exatos |

| Status pHash | Formato | Conteúdos exatos |
| --- | --- | --- |
| SUCCESS | png | 1 |

## 16. Achados técnicos consolidados

### F-001 — exact_media_duplicate

Classificação: DERIVED.

Conteúdo byte a byte idêntico foi verificado em 2 ocorrências catalogadas no snapshot.

Base técnica: Igualdade SHA-256/tamanho verificada na 8A1; report.data_snapshot / 1.0.0.

Provenance: Anchor, referência F-001 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica.

### F-002 — window_exact_candidate

Classificação: DERIVED.

Na janela W-001, um candidate técnico persistido do tipo device foi referenciado por 3 current event(s) da projeção retornada.

Base técnica: exact_match.correlator / 1.0.0; device.exact_namespace_value / 1.0.0.

Provenance: W-001, referência F-002 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica.

### F-003 — window_exact_candidate

Classificação: DERIVED.

Na janela W-001, um candidate técnico persistido do tipo network foi referenciado por 3 current event(s) da projeção retornada.

Base técnica: exact_match.correlator / 1.0.0; network.exact_canonical_ip / 1.0.0.

Provenance: W-001, referência F-003 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica.

### F-004 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-001, dois current events retornados estão separados por 1000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-001, referência F-004 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-005 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-001, dois current events retornados estão separados por 2000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-001, referência F-005 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-006 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-001, dois current events retornados estão separados por 3000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-001, referência F-006 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-007 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-001, dois current events retornados estão separados por 4000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-001, referência F-007 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-008 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-001, dois current events retornados estão separados por 1000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-001, referência F-008 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-009 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-001, dois current events retornados estão separados por 2000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-001, referência F-009 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-010 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-001, dois current events retornados estão separados por 3000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-001, referência F-010 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-011 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-001, dois current events retornados estão separados por 1000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-001, referência F-011 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-012 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-001, dois current events retornados estão separados por 2000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-001, referência F-012 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-013 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-001, dois current events retornados estão separados por 1000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-001, referência F-013 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-014 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-001, o par temporal possui membership técnica compartilhada em 1 candidate(s) exato(s) device, no prefixo retornado sob a policy 6B.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-001, referência F-014 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-015 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-001, o par temporal possui membership técnica compartilhada em 1 candidate(s) exato(s) device, no prefixo retornado sob a policy 6B.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-001, referência F-015 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-016 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-001, o par temporal não possui membership exata compartilhada retornada sob a policy 6B para device/network, no prefixo desta consulta.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-001, referência F-016 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-017 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-001, o par temporal não possui membership exata compartilhada retornada sob a policy 6B para device/network, no prefixo desta consulta.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-001, referência F-017 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-018 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-001, o par temporal possui membership técnica compartilhada em 1 candidate(s) exato(s) device e 1 candidate(s) exato(s) network, no prefixo retornado sob a policy 6B.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-001, referência F-018 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-019 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-001, o par temporal possui membership técnica compartilhada em 1 candidate(s) exato(s) network, no prefixo retornado sob a policy 6B.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-001, referência F-019 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-020 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-001, o par temporal não possui membership exata compartilhada retornada sob a policy 6B para device/network, no prefixo desta consulta.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-001, referência F-020 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-021 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-001, o par temporal possui membership técnica compartilhada em 1 candidate(s) exato(s) network, no prefixo retornado sob a policy 6B.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-001, referência F-021 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-022 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-001, o par temporal não possui membership exata compartilhada retornada sob a policy 6B para device/network, no prefixo desta consulta.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-001, referência F-022 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-023 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-001, o par temporal não possui membership exata compartilhada retornada sob a policy 6B para device/network, no prefixo desta consulta.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-001, referência F-023 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-024 — window_exact_candidate

Classificação: DERIVED.

Na janela W-002, um candidate técnico persistido do tipo device foi referenciado por 3 current event(s) da projeção retornada.

Base técnica: exact_match.correlator / 1.0.0; device.exact_namespace_value / 1.0.0.

Provenance: W-002, referência F-024 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica.

### F-025 — window_exact_candidate

Classificação: DERIVED.

Na janela W-002, um candidate técnico persistido do tipo network foi referenciado por 3 current event(s) da projeção retornada.

Base técnica: exact_match.correlator / 1.0.0; network.exact_canonical_ip / 1.0.0.

Provenance: W-002, referência F-025 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica.

### F-026 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-002, dois current events retornados estão separados por 1000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-002, referência F-026 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-027 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-002, dois current events retornados estão separados por 1000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-002, referência F-027 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-028 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-002, dois current events retornados estão separados por 1000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-002, referência F-028 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-029 — temporal_pair_candidate

Classificação: DERIVED.

Na janela W-002, dois current events retornados estão separados por 1000000 microssegundos dentro do limite de consulta informado.

Base técnica: temporal.proximity / 1.0.0.

Provenance: W-002, referência F-029 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-030 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-002, o par temporal possui membership técnica compartilhada em 1 candidate(s) exato(s) device, no prefixo retornado sob a policy 6B.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-002, referência F-030 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-031 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-002, o par temporal possui membership técnica compartilhada em 1 candidate(s) exato(s) device e 1 candidate(s) exato(s) network, no prefixo retornado sob a policy 6B.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-002, referência F-031 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-032 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-002, o par temporal possui membership técnica compartilhada em 1 candidate(s) exato(s) network, no prefixo retornado sob a policy 6B.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-002, referência F-032 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

### F-033 — temporal_exact_overlap_candidate

Classificação: DERIVED.

Na janela W-002, o par temporal não possui membership exata compartilhada retornada sob a policy 6B para device/network, no prefixo desta consulta.

Base técnica: temporal_exact_overlap / 1.0.0.

Provenance: W-002, referência F-033 no apêndice.

Limitações: A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica. O raio é limite de consulta; delta menor não indica maior força.

## 17. Limitações e afirmações não estabelecidas

- A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica.
- As contagens de cobertura não demonstram completude da realidade.
- A igualdade das seções case-wide verifica coerência dos inputs; não certifica um instante atômico global.
- As verificações de mídia foram realizadas pela 8A1 com leituras e catálogos separados; a 8A2 não as repete.
- Parser runs FAILED: 0 linhas físicas; falha não gera categoria de lacuna automaticamente.
- Mídia não reconhecida: 1 ocorrências catalogadas.
- Ausência no snapshot ou no prefixo não demonstra inexistência de dados, atividade ou vínculo fora do escopo.
- Não há parser WhatsApp implementado nesta versão.

## 18. Lacunas de evidência

### G-001 — Categoria D

O motor contém dados técnicos de mídia e eventos, mas não possui vínculo aprovado media-event nesta versão.

Base técnica: `media.contents.exact_content_count; current_events.total; gap_inputs.media_event_link_available`. Escopo: Anchor / case-wide.

Limitação: Não se atribui qualquer mídia a evento específico; a limitação não identifica uma fonte externa necessária.

Categorias A, E e F não são automatizadas: inexistência não é demonstrada por ausência no snapshot; nova fonte e hipótese exigem pergunta e contexto externos. FAILED e ausência de parser WhatsApp não geram lacuna automaticamente.

## 19. Próximas análises/aquisições recomendadas

- Aprofundar a provenance dos achados conforme a pergunta investigativa.
- Revisar fontes com UNSUPPORTED quando registradas.
- Ampliar janela somente mediante pergunta investigativa documentada.
- Considerar nova fonte apenas quando uma pergunta concreta exigir.

O escopo de WhatsApp permanece condicionado à análise contextual das lacunas. A ausência de parser não fundamenta, por si, sua implementação ou necessidade.

## 20. Apêndice técnico / mapa de provenance

Anchor identifica o único snapshot sem janela; W-IDs identificam as janelas em ordem canônica. F/W/G são referências locais de apresentação, não entidades persistidas. O ponteiro deve ser resolvido no snapshot externo correspondente; nenhum nome de arquivo de input é publicado.

| Finding | Snapshot lógico | Ponteiro |
| --- | --- | --- |
| F-001 | Anchor | finding\_candidates.exact\_media\_duplicate.items[0] |
| F-002 | W-001 | finding\_candidates.window\_exact\_candidate.items[0] |
| F-003 | W-001 | finding\_candidates.window\_exact\_candidate.items[1] |
| F-004 | W-001 | finding\_candidates.temporal\_pair\_candidate.items[0] |
| F-005 | W-001 | finding\_candidates.temporal\_pair\_candidate.items[1] |
| F-006 | W-001 | finding\_candidates.temporal\_pair\_candidate.items[2] |
| F-007 | W-001 | finding\_candidates.temporal\_pair\_candidate.items[3] |
| F-008 | W-001 | finding\_candidates.temporal\_pair\_candidate.items[4] |
| F-009 | W-001 | finding\_candidates.temporal\_pair\_candidate.items[5] |
| F-010 | W-001 | finding\_candidates.temporal\_pair\_candidate.items[6] |
| F-011 | W-001 | finding\_candidates.temporal\_pair\_candidate.items[7] |
| F-012 | W-001 | finding\_candidates.temporal\_pair\_candidate.items[8] |
| F-013 | W-001 | finding\_candidates.temporal\_pair\_candidate.items[9] |
| F-014 | W-001 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[0] |
| F-015 | W-001 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[1] |
| F-016 | W-001 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[2] |
| F-017 | W-001 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[3] |
| F-018 | W-001 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[4] |
| F-019 | W-001 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[5] |
| F-020 | W-001 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[6] |
| F-021 | W-001 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[7] |
| F-022 | W-001 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[8] |
| F-023 | W-001 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[9] |
| F-024 | W-002 | finding\_candidates.window\_exact\_candidate.items[0] |
| F-025 | W-002 | finding\_candidates.window\_exact\_candidate.items[1] |
| F-026 | W-002 | finding\_candidates.temporal\_pair\_candidate.items[0] |
| F-027 | W-002 | finding\_candidates.temporal\_pair\_candidate.items[1] |
| F-028 | W-002 | finding\_candidates.temporal\_pair\_candidate.items[2] |
| F-029 | W-002 | finding\_candidates.temporal\_pair\_candidate.items[3] |
| F-030 | W-002 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[0] |
| F-031 | W-002 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[1] |
| F-032 | W-002 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[2] |
| F-033 | W-002 | finding\_candidates.temporal\_exact\_overlap\_candidate.items[3] |
