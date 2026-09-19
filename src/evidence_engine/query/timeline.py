"""Minimal chronological projection; catalog access is read-only and snapshot-consistent."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Connection, func, select

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import CasePaths
from evidence_engine.models.entities import NormalizedEvent
from evidence_engine.query.policy import POLICY_ID, POLICY_VERSION, current_event_predicate
from evidence_engine.storage.database import open_database

UTC_INPUT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z")


@dataclass(frozen=True)
class TimelineItem:
    event_id: str
    parsed_record_id: str
    occurred_at_utc: str
    platform: str
    event_kind: str
    normalizer_id: str
    normalizer_version: str
    time_status: str
    time_basis: str


@dataclass(frozen=True)
class TimelineResult:
    policy_id: str
    policy_version: str
    matched_total: int
    returned: int
    undated_current_events: int
    truncated: bool
    items: tuple[TimelineItem, ...]


def utc_bound(value: str | None) -> str | None:
    if value is None:
        return None
    if not UTC_INPUT.fullmatch(value):
        raise EvidenceError("Timeline bounds require UTC YYYY-MM-DDTHH:MM:SS[.ffffff]Z")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceError("Invalid UTC timeline bound") from error
    # NormalizedEvent's established UTC storage format has exactly six fractional digits.
    return instant.isoformat(timespec="microseconds").replace("+00:00", "Z")


def query_timeline(
    case_root: Path,
    *,
    start: str | None = None,
    end: str | None = None,
    platform: str | None = None,
    event_kind: str | None = None,
    limit: int = 1000,
) -> TimelineResult:
    start_utc, end_utc = utc_bound(start), utc_bound(end)
    if start_utc is not None and end_utc is not None and start_utc >= end_utc:
        raise EvidenceError("Timeline start must precede end")
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise EvidenceError("Timeline limit must be between 1 and 10000")
    paths = CasePaths.load(case_root)
    engine = open_database(paths.db_file, read_only=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            if connection.exec_driver_sql("PRAGMA user_version").scalar_one() != 5:
                raise EvidenceError("Current timeline requires catalog schema v5")
            return timeline_in_snapshot(
                connection,
                start_utc=start_utc,
                end_utc=end_utc,
                platform=platform,
                event_kind=event_kind,
                limit=limit,
            )
    finally:
        engine.dispose()


def timeline_in_snapshot(
    connection: Connection,
    *,
    start_utc: str | None,
    end_utc: str | None,
    platform: str | None,
    event_kind: str | None,
    limit: int,
) -> TimelineResult:
    """Execute the existing timeline projection in a caller-owned read snapshot.

    Bounds must already be validated and normalized with utc_bound.
    """
    filters = [current_event_predicate()]
    if platform is not None:
        filters.append(NormalizedEvent.platform == platform)
    if event_kind is not None:
        filters.append(NormalizedEvent.event_kind == event_kind)
    # Undated counts use policy/platform/kind, never a fabricated time-window placement.
    undated = connection.scalar(
        select(func.count())
        .select_from(NormalizedEvent)
        .where(*filters, NormalizedEvent.occurred_at_utc.is_(None))
    )
    filters.append(NormalizedEvent.occurred_at_utc.is_not(None))
    if start_utc is not None:
        filters.append(NormalizedEvent.occurred_at_utc >= start_utc)
    if end_utc is not None:
        filters.append(NormalizedEvent.occurred_at_utc < end_utc)
    matched = connection.scalar(select(func.count()).select_from(NormalizedEvent).where(*filters))
    rows = connection.execute(
        select(
            NormalizedEvent.id.label("event_id"),
            NormalizedEvent.parsed_record_id,
            NormalizedEvent.occurred_at_utc,
            NormalizedEvent.platform,
            NormalizedEvent.event_kind,
            NormalizedEvent.normalizer_id,
            NormalizedEvent.normalizer_version,
            NormalizedEvent.time_status,
            NormalizedEvent.time_basis,
        )
        .where(*filters)
        .order_by(
            NormalizedEvent.occurred_at_utc,
            NormalizedEvent.platform,
            NormalizedEvent.event_kind,
            NormalizedEvent.id,
        )
        .limit(limit)
    ).mappings()
    items = tuple(TimelineItem(**row) for row in rows)
    assert matched is not None and undated is not None
    return TimelineResult(
        POLICY_ID, POLICY_VERSION, matched, len(items), undated, matched > len(items), items
    )
