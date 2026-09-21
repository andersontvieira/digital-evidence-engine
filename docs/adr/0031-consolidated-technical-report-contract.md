# ADR 0031 — Consolidated Technical Report Contract

Status: aceito como contrato; implementação 8A1 futura.

## Finalidade e natureza

A 8A0 é exclusivamente documental. Define como consolidar as camadas concluídas
até a 6B no futuro **Relatório Técnico Consolidado de Análise e Organização de
Evidências Digitais**. Também é aceitável o título sem “Consolidado”. O documento
não será apresentado como Laudo Pericial, Perícia Digital Certificada ou Conclusão
Pericial, nem sugerirá certificação formal inexistente.

O relatório deverá identificar os materiais analisados, registrar metodologia e
cadeia técnica, separar extração de derivação, selecionar achados relevantes e
rastreáveis, permitir reprodução e declarar limitações, afirmações não
estabelecidas e lacunas. Orientará análises/aquisições posteriores sem decidir
questões jurídicas ou determinar autoria humana.

A base disponível inclui Foundation/catalogação/SHA-256/provenance; parsers
Meta, Google e Apple; NormalizedEvent; DeviceObservation e NetworkObservation;
CorrelationCandidate/Support exatos persistidos; timeline current, busca técnica,
drill-down de provenance, incident window e candidate matrix; inventário de mídia,
duplicatas exatas, exact content set e pHash JPEG/PNG; pares temporais 6A e overlap
técnico 6B. Schema permanece v5. Nenhuma camada existente ganha capacidade nova
pela redação deste contrato.

## Classificação epistemológica e atribuição

Todo conteúdo analítico relevante deve ter classificação distinguível:

| Classe | Significado |
| --- | --- |
| OBSERVED | Valor ou registro diretamente extraído de fonte catalogada sob contrato de parser/provenance. |
| DERIVED | Resultado calculado a partir dos dados observados, sob policy e versão explícitas. |
| REPORTED | Informação declarada por cliente, operador ou outra fonte humana, não demonstrada automaticamente pelos artefatos. |
| HYPOTHESIS | Possibilidade investigativa ou explicação que ainda exige suporte adicional. |

Não promover REPORTED → OBSERVED ou HYPOTHESIS → DERIVED sem suporte documentado.
Registrar uma declaração não demonstra a veracidade do seu conteúdo. O nome de
uma entidade, inclusive Observation, não basta para classificá-la como OBSERVED:
seu processamento e policy devem ser respeitados; normalizações e features
calculadas permanecem DERIVED, com acesso ao valor extraído original.

Atribuir registros a conta, artefato, registro, device identifier observado,
IP observado/canonicalizado, source record ou plataforma. Preferir “o registro
associado à conta contém...” a atribuir a ação automaticamente a uma pessoa.
Associação de conta/dispositivo a pessoa permanece REPORTED ou HYPOTHESIS até
suporte técnico/documental suficiente para afirmação diferente, com base e
limites explícitos. Nenhuma futura camada gera automaticamente responsável,
culpado, fraude confirmada, autoria humana, intenção, má-fé, crime ou violação
jurídica como conclusão técnica do motor.

## Contrato conceitual de achado e seleção

Cada achado consolidado deverá conter conceitualmente:

| Elemento | Função |
| --- | --- |
| finding_id | Identificador lógico para organização interna do relatório. |
| classification | OBSERVED, DERIVED, REPORTED ou HYPOTHESIS. |
| statement | Descrição factual e limitada ao suporte disponível. |
| technical_basis | Camada, método/policy e versão que sustentam o achado; explicitar quando não houver cálculo técnico. |
| provenance_basis | IDs e referências necessários ao drill-down; para declarações/hipóteses, registrar sua origem e o suporte disponível, sem inventar referência técnica. |
| limitations | O que o achado não demonstra e restrições de cobertura. |
| related_findings | Referências opcionais a outros achados, sem inferência causal. |

Isso não define DTO nem schema JSON. A 8A1 decidirá a projeção computacional após
revisar as APIs. Não inventar valores para campos sem suporte.

Achados não devem repetir todos os registros: selecionar fatos e derivações
materialmente úteis à pergunta investigativa. A seleção deve ser auditável:
registrar query, filtros, janela, policy/versão e motivo de inclusão, distinguindo
o universo consultado do prefixo retornado. Proibir ranking oculto e seleção por
“interesse” não documentado. Referências entre achados não somam força.

## Provenance, números e tempo

Todo achado OBSERVED ou DERIVED relevante deve ter caminho reproduzível até a
provenance existente. Reutilizar event_id, parsed_record_id, device_observation_id,
network_observation_id, candidate_id, EvidenceFile/ArchiveMember, source locator
e SHA-256 catalogado, conforme aplicável. O dataset de suporte 8A1/8A2 deve
preservar as referências necessárias para reconstruir a cadeia até a fonte e
seu container/original. A apresentação humana pode usar notas, tabelas, apêndices
ou referências internas; não precisa imprimir todos os IDs em cada frase.

Toda contagem terá unidade e universo explícitos: linhas físicas de banco,
current events sob policy, ParsedRecords, observations, candidates, supports,
media occurrences, exact contents, temporal pairs ou prefixo retornado. Não
misturar unidades. Quando houver limit, distinguir matched_total, returned e
truncated, ou os nomes equivalentes da query, sem confundir total e amostra.
Distribuições do prefixo, inclusive overlap, não representam automaticamente
todos os pares correspondentes à consulta.

current_event_policy seleciona versões aprovadas de normalizers. Contagens
físicas podem incluir versões históricas; COUNT(normalized_events) não equivale
automaticamente à contagem current. Policy e versão acompanham os números
relevantes, com distinção explícita entre current e histórico.

UTC é canônico somente quando sustentado por informação suficiente. Timestamps
raw e timezone original permanecem acessíveis via provenance; ambiguidades e
ausências são declaradas, sem conversão silenciosa. Renderização local futura
será apresentação, sem mudar o valor canônico. Não é implementada nesta etapa.

## Linguagem permitida e limites técnicos

| Camada | Afirmação técnica permitida | O que não estabelece automaticamente |
| --- | --- | --- |
| Integridade | “O conteúdo analisado coincide com a baseline catalogada”; “SHA-256 permaneceu consistente durante a verificação”; “verify não detectou divergência nos arquivos catalogados consultados”, quando sustentado pela execução e seu escopo. | Autenticidade anterior à aquisição, autoria, origem humana, admissibilidade jurídica ou ausência de manipulação prévia. |
| Duplicatas exatas | Para ocorrências verificadas com mesmo SHA-256: “conteúdo byte a byte idêntico” ou “conteúdo exato compartilhado entre ocorrências catalogadas”. | Mesmo upload, envio, evento, autoria ou origem histórica. Todas as occurrences e provenance continuam acessíveis. |
| pHash | Feature perceptual DERIVED, com método/versionamento explícitos. | “Mesma imagem”, “imagem derivada” ou “imagem editada”. Não há threshold/classificação de similaridade atual. Comparação futura exige contrato específico aprovado. |
| DeviceObservation | Identificador/modelo explicitamente observado em registro suportado; preservar a classificação da camada derivada e a referência ao dado fonte. | Entidade física de dispositivo. Candidate device representa igualdade exata sob regra/versão 3C1, não mesmo aparelho físico, proprietário, pessoa ou sessão. |
| NetworkObservation | Campo IP observado e, quando válido, representação canonical; candidate network é membership por igualdade IP/versão sob policy 3C1. | Mesma pessoa, dispositivo, residência, sessão ou localização física. |
| TemporalPairCandidate | Dois current events com UTC conhecido, na janela e no raio escolhidos pelo operador. max_delta_seconds é retrieval bound. | Threshold probatório; delta menor não é maior força. Proximidade não demonstra causalidade, sessão, pessoa ou dispositivo. |
| Overlap 6B | “Dois eventos temporalmente próximos possuem memberships técnicas compartilhadas em um candidate exato persistido”. | Identidade ou vínculo conclusivo entre pessoas, dispositivos físicos ou sessões. |

pHash não pode ser combinado com eventos: não existe media-event link aprovado.
Não criar esse vínculo por nome, path, tempo ou similaridade.

NAT, VPN, proxies, carrier networks e Wi-Fi compartilhado podem ser mencionados
como limitações gerais quando pertinentes; não atribuir nenhuma dessas
explicações ao caso sem evidência.

Manter device overlap e network overlap separados, sem soma, score ou peso.
Indicar mesmo ParsedRecord quando relevante: o overlap pode vir da mesma
observation e não representa duas fontes independentes. Não usar strong
correlation, high confidence, likely same user, same device ou same session como
conclusões produzidas pelos candidates. Evitar “correlação” sem qualificador
quando puder sugerir causalidade ou identidade; preferir candidate técnico,
proximidade temporal, membership exata compartilhada, overlap técnico ou igualdade
exata sob policy identificada. Não chamar isso de “prova de correlação” ou
“ligação confirmada entre pessoas”.

## Ausência e lacunas de evidência

Afirmações negativas são limitadas a artefato, policy, janela, dataset e versão
consultados, com indicação de cobertura e truncamento. “Nenhum overlap foi
encontrado nesta consulta” não significa inexistência de overlap. “Nenhum evento
foi retornado nesta janela” não demonstra que nenhuma atividade ocorreu.
“Nenhum aparelho adicional aparece neste inventário” não demonstra que nenhum
outro aparelho existiu historicamente. Não transformar ausência em evidência
de diferença nem insuficiência de cobertura em certeza negativa.

A seção obrigatória de lacunas distinguirá:

| Categoria | Lacuna |
| --- | --- |
| A | Dado que não existe nas fontes disponíveis, delimitando a cobertura que sustenta essa constatação. |
| B | Dado existente, ainda sem suporte de parser. |
| C | Dado parseado, mas sem timestamp suficiente. |
| D | Dado disponível, sem vínculo aprovado entre camadas. |
| E | Pergunta investigativa que exige nova fonte. |
| F | Hipótese que ainda necessita suporte. |

Quando não for possível distinguir inexistência de falta de cobertura, registrar
a incerteza em vez de classificar como A por conveniência. A gap analysis da 8A2
orientará se WhatsApp é necessário, períodos/conversas de interesse, campos e
timestamps a preservar e se novo parser agrega valor. Milestone 7 permanece
futura e condicionada a perguntas e lacunas objetivas; não pressupor necessidade
de WhatsApp nem propor parser geral sem pergunta investigativa definida.

## Estrutura base do relatório futuro

1. Identificação do documento.
2. Objetivo e escopo.
3. Natureza e limitações do trabalho.
4. Materiais/evidências analisados.
5. Metodologia técnica.
6. Preservação, integridade e provenance.
7. Fontes e cobertura de parsing: Meta, Google, Apple; outras somente quando implementadas.
8. Normalização temporal.
9. Observações técnicas de dispositivo.
10. Observações técnicas de rede.
11. Candidates por igualdade exata.
12. Timeline e janelas relevantes.
13. Temporal Proximity Candidates.
14. Temporal + Exact Signal Overlap.
15. Análise técnica de mídia: inventory, exact duplicates, exact contents e pHash.
16. Achados técnicos consolidados.
17. Limitações e afirmações não estabelecidas.
18. Lacunas de evidência.
19. Próximas análises/aquisições recomendadas.
20. Apêndice técnico / mapa de provenance.

A 8A2 poderá refinar a ordem, preservando estes princípios e a seção de lacunas.

## Fronteiras de implementação e privacidade

8A0 é esta entrega documental; não conclui o Milestone 8. Não define comando,
DTO ou schema JSON final, não gera prosa, relatório real, PDF/DOCX, parser,
helper ou código funcional. Não altera schema v5 nem dependências.

8A1 — Read-only Report Data Snapshot — definirá a projeção estruturada e
determinística necessária ao relatório, após revisar as APIs existentes. Deve
reutilizar queries, provenance e policies e evitar recalcular fatos produzidos.
Metadata do relatório, resumo do inventário, contagens técnicas, candidatos a
achados, referências e limitações/lacunas são conceitos possíveis, não campos
de schema já aprovados. Não produzir prosa interpretativa automática.

8A2 — First Consolidated Technical Report — consumirá o snapshot da 8A1 para
rendering/consolidação do primeiro relatório do caso e sua gap analysis. Markdown
é uma possibilidade; PDF/DOCX posteriores também, sem escolha ou implementação
de formato nesta 8A0. 8B / dossier final e exports permanecem futuros.

Reports serão consumidores read-only; não alteram o evidence database nem as
evidências. Datasets de suporte e documentos de caso ficam fora do Git, com toda
a provenance disponível. Documentos tracked não podem conter nomes, emails,
telefones, IPs, device/event/candidate IDs, timestamps, paths, hashes, mensagens
ou conteúdo pessoal reais. Exemplos e placeholders devem ser 100% sintéticos.

Não há questão epistemológica bloqueante. APIs/projeção concreta, captura do
contexto das consultas e política de consistência do snapshot serão definidas
na 8A1; apresentação, seleção auditável e formatos serão detalhados nas etapas
correspondentes. O próximo passo é revisar as APIs existentes e propor o escopo
read-only da 8A1 sob este contrato, sem inferência automática ou expansão dos
limites técnicos das camadas consumidoras.
