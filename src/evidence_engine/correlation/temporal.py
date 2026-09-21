"""Transient time-only pair candidates over the existing current-event timeline."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Connection

from evidence_engine.errors import EvidenceError
from evidence_engine.query.catalog import read_catalog, validate_limit
from evidence_engine.query.timeline import TimelineItem, timeline_in_snapshot, utc_bound


@dataclass(frozen=True)
class TemporalPolicy:
    max_delta_seconds: int
    relation_kind: str = "temporal.proximity_candidate"
    policy_id: str = "temporal.proximity"
    policy_version: str = "1.0.0"
    feature_class: str = "DERIVED"


@dataclass(frozen=True)
class TemporalWindow:
    start: str
    end: str
    platform: str | None
    event_kind: str | None


@dataclass(frozen=True)
class TemporalPairCandidate:
    delta_microseconds: int
    event_a: TimelineItem
    event_b: TimelineItem


@dataclass(frozen=True)
class TemporalCandidates:
    policy: TemporalPolicy
    window: TemporalWindow
    eligible_events: int
    matched_pairs: int
    returned_pairs: int
    truncated: bool
    items: tuple[TemporalPairCandidate, ...]


def _sweep_pairs(
    events: tuple[TimelineItem, ...],
    max_delta_seconds: int,
    limit: int,
) -> tuple[int, tuple[TemporalPairCandidate, ...]]:
    """Input is in canonical timeline order; output is lexicographic (A key, B key)."""
    times = [datetime.fromisoformat(event.occurred_at_utc) for event in events]
    bound = max_delta_seconds * 1_000_000
    matched = 0
    items: list[TemporalPairCandidate] = []
    for a, event_a in enumerate(events):
        for b in range(a + 1, len(events)):
            delta = times[b] - times[a]
            microseconds = (
                delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
            )
            if microseconds > bound:
                break
            matched += 1
            if len(items) < limit:
                items.append(TemporalPairCandidate(microseconds, event_a, events[b]))
    return matched, tuple(items)


def temporal_candidates(
    case_root: Path,
    *,
    start: str,
    end: str,
    max_delta_seconds: int,
    platform: str | None = None,
    event_kind: str | None = None,
    limit: int = 1000,
) -> TemporalCandidates:
    start_utc, end_utc = temporal_bounds(start, end, max_delta_seconds, limit)
    with read_catalog(case_root) as connection:
        return temporal_candidates_in_snapshot(
            connection,
            start_utc=start_utc,
            end_utc=end_utc,
            max_delta_seconds=max_delta_seconds,
            platform=platform,
            event_kind=event_kind,
            limit=limit,
        )


def temporal_bounds(start: str, end: str, max_delta_seconds: int, limit: int) -> tuple[str, str]:
    """Shared public-input validation, before opening either temporal query."""
    validate_limit(limit, 10000)
    if type(max_delta_seconds) is not int or not 1 <= max_delta_seconds <= 86400:
        raise EvidenceError("Temporal max_delta_seconds must be between 1 and 86400")
    start_utc, end_utc = utc_bound(start), utc_bound(end)
    if start_utc is None or end_utc is None:
        raise EvidenceError("Temporal candidates require start and end UTC bounds")
    if start_utc >= end_utc:
        raise EvidenceError("Temporal start must precede end")
    return start_utc, end_utc


def temporal_candidates_in_snapshot(
    connection: Connection,
    *,
    start_utc: str,
    end_utc: str,
    max_delta_seconds: int,
    platform: str | None,
    event_kind: str | None,
    limit: int,
) -> TemporalCandidates:
    """Compose in the caller's read snapshot; arguments must already be validated."""
    timeline = timeline_in_snapshot(
        connection,
        start_utc=start_utc,
        end_utc=end_utc,
        platform=platform,
        event_kind=event_kind,
        limit=None,
    )
    matched, items = _sweep_pairs(timeline.items, max_delta_seconds, limit)
    return TemporalCandidates(
        TemporalPolicy(max_delta_seconds),
        TemporalWindow(start_utc, end_utc, platform, event_kind),
        len(timeline.items),
        matched,
        len(items),
        matched > len(items),
        items,
    )
