# 0004 — UTC como tempo canônico

## Status

Aceito como decisão arquitetural; implementação conforme o roadmap.

## Context

Fontes podem conter offsets, zonas, formatos, precisões diferentes ou nenhuma informação de timezone.

## Decision

Correlacionar por UTC quando a conversão for determinável. Preservar timestamp original, timezone original, UTC normalizado e horário local derivado com sua zona. Usar zoneinfo; introduzir python-dateutil quando o parsing justificar.

## Consequences

Não usar a zona da máquina como inferência silenciosa. Ausência, ambiguidade e horários inválidos ficam explícitos e podem impedir normalização. Conversões e suposições terão método e proveniência; a timeline deverá sinalizar eventos sem UTC.
