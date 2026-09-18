"""Small static normalizer contract; no raw-file access or dynamic plugins."""

from dataclasses import dataclass
from typing import Protocol

from evidence_engine.ingest.parsing.framework import JSONValue


@dataclass(frozen=True)
class NormalizerContext:
    parser_id: str
    parser_version: str
    record_type: str
    timestamp_raw: JSONValue
    payload: dict[str, JSONValue]
    annotations: list[dict[str, JSONValue]]


@dataclass(frozen=True)
class EventDraft:
    platform: str
    event_kind: str
    occurred_at_utc: str | None
    time_status: str
    time_basis: str
    ip_raw: JSONValue = None
    device_identifier_raw: JSONValue = None
    device_model_raw: JSONValue = None
    action_raw: JSONValue = None
    status_raw: JSONValue = None


@dataclass(frozen=True)
class NormalizationResult:
    event: EventDraft
    warnings: tuple[str, ...] = ()


class Normalizer(Protocol):
    @property
    def normalizer_id(self) -> str: ...

    @property
    def normalizer_version(self) -> str: ...

    def supports(self, parser_id: str, parser_version: str, record_type: str) -> bool: ...

    def normalize(self, context: NormalizerContext) -> NormalizationResult: ...
