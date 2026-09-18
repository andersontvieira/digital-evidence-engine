"""Static observer contracts and field provenance, without raw-file access."""

from dataclasses import dataclass
from typing import Protocol

from evidence_engine.ingest.parsing.framework import JSONValue, resolve_locator


@dataclass(frozen=True)
class ObservationContext:
    parser_id: str
    parser_version: str
    record_type: str
    source_locator: str
    payload: dict[str, JSONValue]
    annotations: list[dict[str, JSONValue]]


@dataclass(frozen=True)
class DeviceDraft:
    platform: str
    fact_kind: str
    namespace: str
    value_raw: JSONValue
    source_field_locator: str
    source_field_name: str | None


@dataclass(frozen=True)
class NetworkDraft:
    platform: str
    source_role: str
    ip_raw: JSONValue
    ip_canonical: str | None
    ip_version: int | None
    source_field_locator: str
    source_field_name: str | None


@dataclass(frozen=True)
class ObservationResult:
    observations: tuple[DeviceDraft | NetworkDraft, ...]
    warnings: tuple[str, ...] = ()


class Observer(Protocol):
    @property
    def observer_id(self) -> str: ...

    @property
    def observer_version(self) -> str: ...

    def supports(self, parser_id: str, parser_version: str, record_type: str) -> bool: ...

    def observe(self, context: ObservationContext) -> ObservationResult: ...


def field_value(context: ObservationContext, locator: str) -> JSONValue:
    """Resolve an original field locator relative to this ParsedRecord only."""
    if not locator.startswith(context.source_locator + "/"):
        raise ValueError("FIELD_OUTSIDE_PARSED_RECORD")
    return resolve_locator(context.payload, "$" + locator[len(context.source_locator) :])
