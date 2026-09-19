"""Explicit current-event policy; never select a version by recency or maximum."""

from sqlalchemy import ColumnElement, tuple_

from evidence_engine.models.entities import NormalizedEvent

POLICY_ID = "current_event_policy"
POLICY_VERSION = "1.0.0"
CURRENT_NORMALIZERS = (
    ("meta.event_normalizer", "1.0.0"),
    ("google.event_normalizer", "1.1.0"),
    ("apple.event_normalizer", "1.0.0"),
)


def current_event_predicate() -> ColumnElement[bool]:
    return tuple_(NormalizedEvent.normalizer_id, NormalizedEvent.normalizer_version).in_(
        CURRENT_NORMALIZERS
    )
