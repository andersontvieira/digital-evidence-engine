# Modelo conceitual de evidências

Este documento orienta a Milestone 1 e seguintes. Não define tabelas implementadas
nem garante propriedades que ainda não foram verificadas em um pipeline real.

## Cadeia de proveniência

```text
NormalizedRecord (registro/evento lógico)
  -> suporte(s): SourceRecord (ocorrência localizada na fonte)
    -> EvidenceFile (arquivo extraído ou original sem container)
      -> EvidenceFile pai/container, quando houver
        -> EvidenceFile original + SHA-256 de seu conteúdo
```

| Conceito futuro | Informação a preservar |
| --- | --- |
| Manifesto de aquisição | ID da aquisição/exportação, inventário, horário conhecido, método e versão |
| EvidenceFile | ID da ocorrência, nome/path relativo, papel original/extraído/derivado, tamanho, SHA-256, referência ao pai e à aquisição |
| SourceRecord | ID, arquivo de origem, localização (JSON pointer, linha, seção etc.), parser e versão, representação de origem ou referência verificável |
| NormalizedRecord | ID lógico, tipo, valores normalizados e todos os vínculos de suporte |
| Transformação/afirmação | Natureza epistemológica, entradas, regra/método, versão, resultado e limitações |

Cada arquivo extraído terá hash próprio e referência ao container; arquivos
recebidos diretamente não precisam de um container artificial. Containers
aninhados manterão a cadeia completa, sem ciclos. Paths sozinhos não são identidade
estável, e hashes não substituem IDs de ocorrência. Nenhum dado será inventado para
preencher campos obrigatórios: o contrato deverá permitir ausência com motivo.

## Fatos e interpretação

| Nível | Significado | Exemplo inteiramente sintético |
| --- | --- | --- |
| OBSERVED | Valor encontrado na fonte, sem atestar sua verdade externa | Campo contém `SYNTHETIC-DEVICE-X` |
| DERIVED | Resultado de transformação explícita | Conversão de um horário com offset conhecido para UTC |
| REPORTED | Afirmação atribuída a uma fonte declarante | Relato sintético associa um equipamento a um ator de teste |
| HYPOTHESIS | Interpretação a verificar | Dois registros podem corresponder a uma mesma sessão |

Essas categorias pertencem às afirmações, inclusive por campo; um evento pode
combinar um valor observado e um timestamp derivado sem perder a distinção.
DERIVED exige método/versão e entradas, REPORTED exige atribuição conhecida ou
ausência explícita, HYPOTHESIS exige justificativa e suporte. Contradições serão
preservadas. Confiança, se adicionada, não poderá converter hipótese em observação.

## Representação temporal

Preservar separadamente timestamp original (inclusive sua precisão e formato),
timezone/offset original quando fornecido, UTC normalizado quando determinável,
horário local derivado e identificador da zona usada nessa derivação.

Não interpretar timestamp sem timezone usando a zona da máquina. Horários ambíguos
ou inexistentes em mudanças de horário de verão não serão resolvidos silenciosamente.
UTC pode permanecer ausente com estado `missing`, `ambiguous` ou `invalid` conceitual;
esses estados não constituem enums implementados nesta entrega. Uma suposição
fornecida pelo operador será registrada como derivação explícita, sem sobrescrever
o valor original. Eventos sem UTC determinado não serão ordenados como se o tivessem.

## Deduplicação e identidade

Conteúdo byte a byte idêntico pode compartilhar SHA-256, mas ocorrências distintas
continuam com referências e aquisições próprias. Um evento lógico poderá ter
suportes N:N com SourceRecord. Critério e versão de deduplicação serão registrados;
fontes discordantes não poderão ser descartadas nem sobrescritas pela última importação.
Reimportação deverá ser idempotente dentro de um critério documentado e preservar
histórico de execução. Regras incertas produzirão candidatos a correlação, não fusões
destrutivas. Hash perceptual medirá similaridade de mídia, nunca identidade exata.

## Limites de garantia

SHA-256 permite verificar consistência de conteúdo com o hash registrado. Não
comprova autoria, autenticidade anterior à aquisição ou validade jurídica. O motor
não é software pericial certificado. A rastreabilidade descreve o processamento
técnico e suas fontes sem prometer certificação de cadeia de custódia.
