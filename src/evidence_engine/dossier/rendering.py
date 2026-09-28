"""Deterministic bounded Markdown from presentation DTOs only; no I/O."""

import json
from collections.abc import Iterable, Sequence

from evidence_engine.dossier.projection import (
    ACCOUNT_KINDS,
    CLASS_ORDER,
    AnnexIndexEntry,
    CoverageRow,
    EventCount,
    HumanDossierProjection,
    Measure,
    SelectionMetadata,
    WindowDisplay,
    require,
    single_line,
)
from evidence_engine.errors import EvidenceError

MAX_GENERATED_FILE_BYTES = 64 * 1024 * 1024
TITLE = "Dossiê Técnico de Organização de Evidências Digitais"
SECTIONS = (
    "Identificação do documento",
    "Finalidade",
    "Escopo e limitações",
    "Fontes e materiais técnicos",
    "Metodologia técnica",
    "Cronologia técnica relevante",
    "Atividades digitais relevantes",
    "Relações técnicas entre fontes e mídias",
    "Comunicações e anexos",
    "Contexto técnico de dispositivos",
    "Contexto técnico de rede",
    "Atividades e alterações de conta",
    "O que os dados estabelecem e o que não estabelecem",
    "Mapa de provenance e índice de anexos",
)
EMPTY = (
    "Os artefatos canônicos selecionados não fornecem dados aprovados para esta seção; "
    "isso não demonstra ausência de atividade fora desse escopo."
)
SCOPE_LIMIT = (
    "A completude é interna ao pacote selecionado; não abrange todas as janelas possíveis "
    "do caso nem toda atividade no mundo real. Ausência nos artefatos selecionados não "
    "demonstra ausência de atividade fora desse escopo."
)
NON_ESTABLISHMENT = (
    "Os dados técnicos não estabelecem automaticamente identidade humana, autoria, "
    "titularidade de conta, propriedade de dispositivo, sessão, causalidade ou conclusão jurídica."
)
WHATSAPP = (
    "WhatsApp está fora do dataset técnico representado nesta versão, condicionado a futura "
    "aquisição/parser/análise separadamente aprovada."
)
ATTACHMENTS = "Anexos de mensagens sem vínculo resolvido permanecem SOURCE_LIMITATION."
SOURCE_MEDIA = (
    "Referência de fonte OBSERVED; resolução/link DERIVED. Cobertura parcial da policy atual. "
    "occurrence_count representa ocorrências catalogadas do conteúdo exato, não envios, "
    "publicações, destinatários ou ações. Member-only representa membro de arquivo verificado "
    "sem ExactMediaContent correspondente sob a policy atual; não significa arquivo inválido "
    "nem implica vídeo. O vínculo não estabelece upload, envio, exclusão ou autoria."
)
CAPTION_WARNING = "Legenda contextual fornecida pelo operador — não constitui finding técnico."
PURPOSES = {
    "consolidated_report": "Relatório técnico canônico detalhado.",
    "report_snapshot": "Snapshot canônico de suporte ao relatório.",
    "technical_review": "Revisão técnica suplementar separada, sem alimentar a narrativa canônica.",
    "structured_support": (
        "Suporte estruturado suplementar separado, sem alimentar a narrativa canônica."
    ),
    "validation_report": "Artefato de validação separado; sua inclusão não cria conclusão técnica.",
    "contextual_visual": (
        "Imagem selecionada para visualização contextual, "
        "sem vínculo automático com evento ou finding."
    ),
}
POLICY_ROLES = {
    "current_event_policy": "Seleção técnica de current events.",
    "eligible_normalizers": "Normalização elegível declarada.",
    "observers": "Observações técnicas declaradas.",
    "exact_rules": "Regra de igualdade exata declarada.",
    "exact_correlator": "Candidates por igualdade exata.",
    "temporal_proximity": "Candidates de proximidade temporal.",
    "temporal_exact_overlap": "Membership exata em pares temporais.",
    "perceptual_hash": "Hash perceptual de imagem; sem linking nesta apresentação.",
    "source_media_links": "Provenance exata entre referência de fonte e mídia.",
}


def escape_text(value: str) -> str:
    """One plain-text strategy for all dynamic cells/prose, never templates."""
    text = single_line(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "".join("\\" + c if c in "\\`*_{}[]()#|!" else c for c in text)


class _Builder:
    """Accept small UTF-8 chunks only within the independent per-file budget."""

    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.size = 0

    def append(self, text: str) -> None:
        chunk = text.encode("utf-8")
        require(self.size + len(chunk) <= MAX_GENERATED_FILE_BYTES, "RESOURCE_LIMIT")
        self.chunks.append(chunk)
        self.size += len(chunk)

    def block(self, text: str) -> None:
        if self.chunks:
            self.append("\n")
        self.append(text)
        self.append("\n")

    def table(self, headers: Sequence[str], rows: Iterable[Sequence[str | int]]) -> None:
        if self.chunks:
            self.append("\n")
        self.row(headers)
        self.row(tuple("---" for _ in headers))
        for row in rows:
            self.row(row)

    def row(self, values: Sequence[str | int]) -> None:
        self.append("| ")
        for index, value in enumerate(values):
            if index:
                self.append(" | ")
            self.append(escape_text(str(value)))
        self.append(" |\n")

    def finish(self) -> bytes:
        # Every block/row contributes its final LF as a budgeted chunk.
        return b"".join(self.chunks)


def _measures(b: _Builder, rows: tuple[Measure, ...]) -> None:
    b.table(("Medida", "Contagem", "Unidade"), ((r.name, r.count, r.unit) for r in rows))


def _coverage(b: _Builder, rows: tuple[CoverageRow, ...]) -> None:
    if not rows:
        b.block(EMPTY)
    else:
        b.table(
            ("Componente", "Versão", "Status/plataforma", "Contagem", "Unidade"),
            ((r.component_id, r.version, r.status_or_platform, r.count, r.unit) for r in rows),
        )


def _events(b: _Builder, rows: tuple[EventCount, ...]) -> None:
    if not rows:
        b.block(EMPTY)
    else:
        b.table(
            ("Plataforma", "Event kind", "Total current", "Datados", "Sem UTC"),
            ((r.platform, r.event_kind, r.total, r.dated, r.undated) for r in rows),
        )


def _window_scope(b: _Builder, w: WindowDisplay) -> None:
    b.table(
        (
            "Início UTC inclusivo",
            "Fim UTC exclusivo",
            "Plataforma",
            "Event kind",
            "Raio contratado em segundos",
            "Current sem UTC",
            "Elegíveis datados",
        ),
        (
            (
                w.start,
                w.end,
                w.platform or "sem filtro",
                w.event_kind or "sem filtro",
                w.max_delta_seconds,
                w.undated_current_events,
                w.eligible_events,
            ),
        ),
    )


def _incidents(b: _Builder, windows: tuple[WindowDisplay, ...], *, accounts: bool = False) -> None:
    if not windows:
        b.block(EMPTY)
    for window in windows:
        b.block("### " + escape_text(window.window_id))
        if not accounts:
            _window_scope(b, window)
            b.table(
                ("Componente", "Unidade", "Total", "Retornado", "Truncado"),
                (
                    (c.component, c.unit, c.total, c.returned, "sim" if c.truncated else "não")
                    for c in window.counts
                ),
            )
        rows = tuple(r for r in window.incidents if not accounts or r.event_kind in ACCOUNT_KINDS)
        if not rows:
            b.block(EMPTY)
            continue
        b.table(
            ("UTC", "Plataforma", "Event kind", "Posição no snapshot"),
            ((r.occurred_at_utc, r.platform, r.event_kind, r.pointer) for r in rows),
        )


def _render_dossier(p: HumanDossierProjection) -> bytes:
    b = _Builder()
    b.block("# " + TITLE)

    def section(number: int) -> None:
        b.block(f"## {number}. {SECTIONS[number - 1]}")

    section(1)
    identity = p.identity
    b.block("Apresentação humana sob ADRs 0036/0037; política de seleção dossier.selection/1.0.0.")
    b.table(
        ("Campo", "Valor"),
        (
            ("report_policy_id", identity.report_policy_id),
            ("report_policy_version", identity.report_policy_version),
            ("snapshot_policy_id", identity.snapshot_policy_id),
            ("snapshot_policy_version", identity.snapshot_policy_version),
            ("evidence_schema_version", identity.evidence_schema_version),
            ("engine_version", identity.engine_version),
            ("delivery_profile", identity.delivery_profile),
        ),
    )
    if identity.issued_date is not None:
        b.block(
            "Data documental fornecida pelo operador: "
            + escape_text(identity.issued_date)
            + ". Não é tempo de evidência nem generated_at."
        )
    if identity.case_reference is not None:
        b.block(
            "Referência opaca fornecida pelo operador: "
            + escape_text(identity.case_reference)
            + ". Token documental, sem atribuição de identidade, processo ou tribunal."
        )
    section(2)
    b.block(
        "Organizar e apresentar material técnico canônico aprovado para revisão humana e "
        "jurídica. A apresentação preserva os achados e limites dos artefatos selecionados."
    )
    section(3)
    b.block(SCOPE_LIMIT)
    b.block(NON_ESTABLISHMENT)
    for limit in p.limitations:
        b.block(escape_text(limit))
    for w in p.windows:
        b.block("### " + escape_text(w.window_id))
        _window_scope(b, w)
        if w.truncated_components:
            b.block(
                "Componentes truncados; achados limitados ao prefixo: "
                + escape_text(", ".join(w.truncated_components))
                + "."
            )
    section(4)
    b.block("Inventário catalogado em unidades físicas; não representa completude do mundo real.")
    _measures(b, p.inventory)
    _coverage(b, p.parser_runs)
    b.block("### Seleção administrativa")
    b.table(
        ("Label local", "Classe", "Papel"),
        ((m.local_label, m.source_class, m.role) for m in p.materials),
    )
    section(5)
    b.block(
        "Policies declaradas; disponibilidade não implica execução. Esta apresentação não "
        "executa verify, parsing, correlação, query ou nova verificação de mídia."
    )
    b.table(
        ("Policy/componente", "Versão", "Papel técnico"),
        ((r.policy_id, r.version, POLICY_ROLES[r.component]) for r in p.policies),
    )
    section(6)
    b.block(
        "Linhas do prefixo de cada janela, na ordem do snapshot. Janelas sobrepostas "
        "permanecem separadas, sem deduplicação ou composição de timeline global."
    )
    _incidents(b, p.windows)
    section(7)
    c = p.current_events
    b.table(
        ("Policy", "Versão", "Unidade", "Total", "Datados", "Sem UTC"),
        ((c.policy_id, c.policy_version, c.unit, c.total, c.dated, c.undated),),
    )
    _events(b, c.rows)
    if not p.findings:
        b.block(EMPTY)
    for finding in p.findings:
        b.block("### " + escape_text(finding.finding_id))
        b.table(("Tipo", "Classe"), ((finding.candidate_type, finding.classification),))
        b.block(escape_text(finding.statement))
        b.block("Base técnica: " + escape_text(finding.technical_basis))
        b.table(
            ("Referência", "Snapshot", "Posição lógica"),
            ((finding.reference.local_id, finding.reference.snapshot, finding.reference.pointer),),
        )
        b.block("Limitações: " + escape_text(finding.limitations))
    section(8)
    b.block(SOURCE_MEDIA)
    links = tuple(f for f in p.findings if f.candidate_type == "source_media_provenance_link")
    if links:
        b.table(
            ("Achado existente", "Snapshot", "Posição lógica"),
            ((f.finding_id, f.reference.snapshot, f.reference.pointer) for f in links),
        )
    else:
        b.block(EMPTY)
    _measures(b, p.media)
    for w in p.windows:
        b.block("### " + escape_text(w.window_id))
        b.table(
            ("Componente", "Unidade", "Total", "Retornado", "Truncado"),
            (
                (c.component, c.unit, c.total, c.returned, "sim" if c.truncated else "não")
                for c in w.counts
                if c.component == "source_media_links"
            ),
        )
        b.block(
            "Status counts abrangem todos os itens correspondentes, "
            "não somente o prefixo retornado."
        )
        _measures(b, w.source_media_statuses)
    section(9)
    _events(b, tuple(r for r in p.current_events.rows if r.event_kind == "communication.message"))
    b.block(ATTACHMENTS)
    b.block(WHATSAPP)
    for number, context, kind in ((10, p.device, "device"), (11, p.network, "network")):
        section(number)
        _coverage(b, context.rows)
        b.table(
            ("Tipo", "Candidates exatos", "Unidade"),
            ((kind, context.exact_candidates, context.candidate_unit),),
        )
        b.block(NON_ESTABLISHMENT)
        b.block("As limitações canônicas da seção 3 permanecem aplicáveis a estas contagens.")
    section(12)
    b.block("Contagens case-wide de current events; não somar às linhas de janelas abaixo.")
    _events(b, tuple(r for r in p.current_events.rows if r.event_kind in ACCOUNT_KINDS))
    b.block("Linhas de incident-window por janela, sem deduplicar sobreposições.")
    _incidents(b, p.windows, accounts=True)
    b.block(NON_ESTABLISHMENT)
    section(13)
    b.block(
        "Os artefatos canônicos selecionados representam os achados referenciados neste "
        "dossiê, dentro dos escopos e prefixos declarados."
    )
    b.table(
        (
            "Achados existentes",
            "Janelas selecionadas",
            "Lacunas documentadas",
            "Achados source-media",
        ),
        ((len(p.findings), len(p.windows), len(p.gaps), len(links)),),
    )
    b.block(NON_ESTABLISHMENT)
    b.block(ATTACHMENTS)
    b.block(WHATSAPP)
    b.block(SCOPE_LIMIT)
    b.block("Os escopos, truncamentos e limitações da seção 3 permanecem aplicáveis.")
    b.block(SOURCE_MEDIA)
    for gap in p.gaps:
        if gap.category == "D":
            b.block(escape_text(gap.statement))
    section(14)
    b.block("Relatório detalhado: technical/canonical/consolidated-report.md")
    b.table(
        ("Snapshot", "Label local", "Destino canônico no pacote"),
        ((s.reference, s.local_label, s.package_path) for s in p.snapshots),
    )
    b.table(
        ("F-ID existente", "Snapshot", "Posição lógica"),
        ((r.local_id, r.snapshot, r.pointer) for r in p.references),
    )
    b.block("[Índice de anexos](annex-index.md)")
    return b.finish()


def render_dossier_markdown(projection: HumanDossierProjection) -> bytes:
    """Serialize the safe projection; each accepted chunk counts against 64 MiB."""
    try:
        return _render_dossier(projection)
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None


def render_annex_index(entries: Sequence[AnnexIndexEntry]) -> bytes:
    """Index approved DTOs; does not imply that any package file was created."""
    try:
        ordered = tuple(entries)
        labels: set[str] = set()
        paths: set[str] = set()
        for entry in ordered:
            require(isinstance(entry, AnnexIndexEntry), "INVALID_SELECTION")
            require(entry.package_path.casefold() not in paths, "INVALID_PATH")
            require(entry.local_label not in labels, "INVALID_SELECTION")
            paths.add(entry.package_path.casefold())
            labels.add(entry.local_label)
        b = _Builder()
        b.block("# Índice de anexos")
        for source_class in CLASS_ORDER:
            group = sorted(
                (e for e in ordered if e.source_class == source_class),
                key=lambda e: (e.role, e.local_label),
            )
            if not group:
                continue
            b.block("## " + escape_text(source_class))
            for entry in group:
                b.block("### " + escape_text(entry.local_label))
                b.table(
                    ("Classe", "Papel", "Destino no pacote"),
                    ((entry.source_class, entry.role, entry.package_path),),
                )
                b.block(PURPOSES[entry.role])
                if entry.display_caption is not None:
                    b.block(escape_text(entry.display_caption))
                    b.block(CAPTION_WARNING)
        b.block("## Arquivos gerados previstos no pacote directory-v1")
        b.block(
            "Lista administrativa de saídas previstas para geração na montagem futura do pacote; "
            "não são artefatos de evidência selecionados. Esta lista não afirma que os arquivos "
            "já existem."
        )
        b.block(
            "- human/dossier.md\n"
            "- human/annex-index.md\n"
            "- technical/selection-metadata.json\n"
            "- integrity/manifest.json\n"
            "- integrity/SHA256SUMS.txt"
        )
        return b.finish()
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None


def render_selection_metadata(metadata: SelectionMetadata) -> bytes:
    """Exact administrative schema, streamed JSON encoding under the output cap."""
    try:
        items: list[dict[str, str | bool]] = []
        labels: set[str] = set()
        paths: set[str] = set()
        for item in sorted(metadata.items, key=lambda i: (i.role, i.local_label)):
            require(item.local_label not in labels, "INVALID_SELECTION")
            require(item.package_path.casefold() not in paths, "INVALID_PATH")
            labels.add(item.local_label)
            paths.add(item.package_path.casefold())
            row: dict[str, str | bool] = {
                "local_label": item.local_label,
                "source_class": item.source_class,
                "role": item.role,
                "package_path": item.package_path,
            }
            if item.role == "contextual_visual":
                require(item.display_caption is not None, "PRIVACY_CONTRACT_VIOLATION")
                row.update(
                    display_caption=item.display_caption or "",
                    operator_selected=True,
                    display_approved=True,
                )
            items.append(row)
        value: dict[str, object] = {
            "policy_id": "dossier.selection",
            "policy_version": "1.0.0",
            "delivery_profile": "directory-v1",
            "items": items,
        }
        if metadata.issued_date is not None:
            value["issued_date"] = metadata.issued_date
        if metadata.case_reference is not None:
            value["case_reference"] = metadata.case_reference
        builder = _Builder()
        encoder = json.JSONEncoder(
            ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        for chunk in encoder.iterencode(value):
            builder.append(chunk)
        builder.append("\n")
        return builder.finish()
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
