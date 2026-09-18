"""Only explicit timezone or source-defined epoch units can produce UTC."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from evidence_engine.ingest.parsing.framework import JSONValue

ISO_ZONE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):?[0-5]\d| UTC)"
)


@dataclass(frozen=True)
class NormalizedTime:
    utc: str | None
    status: str
    basis: str


def normalize_google_time(raw: JSONValue) -> NormalizedTime:
    """Google 1.1.0 only: exact source-declared UTC, plus existing contracts."""
    if isinstance(raw, str) and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} Z", raw
    ):
        try:
            instant = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S Z").replace(tzinfo=UTC)
            return NormalizedTime(
                instant.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "normalized",
                "explicit_utc",
            )
        except ValueError:
            return NormalizedTime(None, "raw_only", "unknown")
    return normalize_time(raw)


def normalize_time(raw: JSONValue, epoch_unit: str | None = None) -> NormalizedTime:
    if raw is None or raw == "":
        return NormalizedTime(None, "missing", "unknown")
    try:
        if type(raw) is int and epoch_unit in {"seconds", "milliseconds"}:
            # No magnitude heuristic and no float rounding of milliseconds.
            instant = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
                microseconds=raw * (1000000 if epoch_unit == "seconds" else 1000)
            )
            basis = "epoch_" + epoch_unit
        elif isinstance(raw, str) and ISO_ZONE.fullmatch(raw):
            instant = datetime.fromisoformat(raw.replace(" UTC", "+00:00").replace("Z", "+00:00"))
            if instant.utcoffset() is None:
                return NormalizedTime(None, "raw_only", "unknown")
            instant = instant.astimezone(UTC)
            basis = "explicit_utc" if raw.endswith(("Z", " UTC")) else "explicit_offset"
        else:
            return NormalizedTime(None, "raw_only", "unknown")
        return NormalizedTime(
            instant.isoformat(timespec="microseconds").replace("+00:00", "Z"), "normalized", basis
        )
    except (ValueError, OverflowError):
        return NormalizedTime(None, "raw_only", "unknown")
