import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.parsing.service import parse_instagram
from evidence_engine.models.entities import (
    ArchiveMember,
    DeviceObservation,
    EvidenceFile,
    NetworkObservation,
    ObservationRun,
    ParsedRecord,
    SourceRecord,
)
from evidence_engine.normalization.normalizers import PlatformNormalizer
from evidence_engine.normalization.service import normalize_events
from evidence_engine.observations.framework import ObservationContext, field_value
from evidence_engine.observations.observers import OBSERVERS
from evidence_engine.observations.service import observe_device_network
from evidence_engine.storage.database import V3_TABLES, open_database
from tests.test_normalization_service import populated
from tests.test_parsing_service import synthetic_zip


def old_rows(root):
    with sqlite3.connect(root / "database/evidence.db") as c:
        return {t: c.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in V3_TABLES}


def test_observe_catalog_only_provenance_idempotence_and_old_rows(case_root, monkeypatch):
    populated(case_root)
    normalize_events(case_root, (PlatformNormalizer("google", "1.0.0"),))
    normalize_events(case_root)
    before = old_rows(case_root)
    original_open = Path.open

    def forbid_evidence(path, *args, **kwargs):
        assert "originals" not in path.parts and "working" not in path.parts
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", forbid_evidence)
        result = CliRunner().invoke(
            app, ["observe", "device-network", "--case-root", str(case_root)]
        )
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["errors"] == 0
    assert (
        summary["device_observations_created"] > 0 and summary["network_observations_created"] > 0
    )
    assert all(isinstance(value, int) for value in summary.values())
    assert "SYNTHETIC" not in result.output and "203.0.113" not in result.output
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        ids = {}
        for model in (DeviceObservation, NetworkObservation):
            facts = list(s.scalars(select(model)))
            ids[model] = {f.id for f in facts}
            for fact in facts:
                record = s.get(ParsedRecord, fact.parsed_record_id)
                source = s.get(SourceRecord, record.source_record_id)
                member = s.get(ArchiveMember, source.archive_member_id)
                evidence = s.get(EvidenceFile, member.evidence_file_id)
                assert (
                    hashlib.sha256(
                        (case_root / "originals" / evidence.relative_path).read_bytes()
                    ).hexdigest()
                    == evidence.sha256
                )
                ctx = ObservationContext(
                    record.parser_id,
                    record.parser_version,
                    record.record_type,
                    record.source_locator,
                    json.loads(record.payload_json),
                    json.loads(record.annotations_json),
                )
                value = json.loads(
                    fact.value_raw if isinstance(fact, DeviceObservation) else fact.ip_raw
                )
                source_value = field_value(ctx, fact.source_field_locator)
                if isinstance(fact, DeviceObservation) and fact.namespace.endswith(
                    "user_agent.model_code"
                ):
                    assert value in source_value
                else:
                    assert value == source_value
        assert {r.status for r in s.scalars(select(ObservationRun))} == {"COMPLETED"}
    again = observe_device_network(case_root)
    assert (
        again.errors == again.device_observations_created == again.network_observations_created == 0
    )
    assert again.device_observations_existing == len(ids[DeviceObservation])
    assert again.network_observations_existing == len(ids[NetworkObservation])
    with Session(engine) as s:
        for model in ids:
            assert {f.id for f in s.scalars(select(model))} == ids[model]
    assert old_rows(case_root) == before
    engine.dispose()


def test_existing_observation_mismatch_is_not_overwritten(case_root):
    populated(case_root)
    assert observe_device_network(case_root).errors == 0
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        fact = s.scalars(select(DeviceObservation)).first()
        fact_id = fact.id
        fact.value_raw = json.dumps("SYNTHETIC-CHANGED-DERIVED-VALUE")
        s.commit()
        count = len(list(s.scalars(select(DeviceObservation))))
    summary = observe_device_network(case_root)
    assert summary.errors == 1 and summary.device_observations_created == 0
    assert summary.network_observations_existing > 0
    with Session(engine) as s:
        assert (
            json.loads(s.get(DeviceObservation, fact_id).value_raw)
            == "SYNTHETIC-CHANGED-DERIVED-VALUE"
        )
        assert len(list(s.scalars(select(DeviceObservation)))) == count
    engine.dispose()


@pytest.mark.parametrize("failed_index", [0, 1])
def test_midrun_failure_atomic_and_other_observer_continues(case_root, failed_index):
    populated(case_root)
    original = OBSERVERS[failed_index]

    class Broken:
        observer_id = original.observer_id
        observer_version = original.observer_version
        supports = original.supports
        calls = 0

        def observe(self, ctx):
            result = original.observe(ctx)
            if result.observations:
                self.calls += 1
                if self.calls == 2:
                    raise ValueError("SYNTHETIC_PRIVATE_ERROR")
            return result

    observers = list(OBSERVERS)
    observers[failed_index] = Broken()
    summary = observe_device_network(case_root, tuple(observers))
    assert summary.errors == 1
    engine = open_database(case_root / "database/evidence.db")
    failed_model, good_model = (
        (DeviceObservation, NetworkObservation)
        if failed_index == 0
        else (NetworkObservation, DeviceObservation)
    )
    with Session(engine) as s:
        assert list(s.scalars(select(failed_model))) == []
        good_ids = set(s.scalars(select(good_model.id)))
        assert good_ids
        run = s.scalars(
            select(ObservationRun).where(ObservationRun.observer_id == original.observer_id)
        ).one()
        assert run.status == "FAILED" and run.error_code == "OBSERVATION_ERROR"
        assert run.observations_created == 0 and "PRIVATE" not in run.warnings_json
    assert observe_device_network(case_root).errors == 0
    with Session(engine) as s:
        assert set(s.scalars(select(good_model.id))) == good_ids
    engine.dispose()


def test_multiple_sources_and_repeated_values_never_merge(case_root):
    for name in ("synthetic-a.zip", "synthetic-b.zip"):
        synthetic_zip(case_root, name)
    (case_root / "originals/profile_activity.json").write_text(
        json.dumps(
            {
                "profile_account_insights": [
                    {"device_id": "SYNTHETIC-ID", "ip_address": "203.0.113.10"},
                    {"device_id": "SYNTHETIC-ID", "ip_address": "203.0.113.10"},
                    {"device_id": "SYNTHETIC-ID"},
                ]
            }
        )
    )
    ingest(case_root)
    assert parse_instagram(case_root).errors == 0
    assert observe_device_network(case_root).errors == 0
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        direct = [
            r
            for r in s.scalars(select(ParsedRecord))
            if s.get(SourceRecord, r.source_record_id).evidence_file_id
        ]
        assert len(direct) == 3
        ids = [r.id for r in direct]
        devices = list(
            s.scalars(select(DeviceObservation).where(DeviceObservation.parsed_record_id.in_(ids)))
        )
        ips = list(
            s.scalars(
                select(NetworkObservation).where(NetworkObservation.parsed_record_id.in_(ids))
            )
        )
        assert len(devices) == 3 and len(ips) == 2
        assert len({f.value_raw for f in devices}) == len({f.ip_raw for f in ips}) == 1
        for fact in [*devices, *ips]:
            record = s.get(ParsedRecord, fact.parsed_record_id)
            source = s.get(SourceRecord, record.source_record_id)
            evidence = s.get(EvidenceFile, source.evidence_file_id)
            assert source.archive_member_id is None and len(evidence.sha256) == 64
        archived = [
            r
            for r in s.scalars(select(ParsedRecord))
            if s.get(SourceRecord, r.source_record_id).archive_member_id
        ]
        assert len({r.payload_json for r in archived}) < len(archived)
        observations = list(
            s.scalars(
                select(NetworkObservation).where(NetworkObservation.parsed_record_id.not_in(ids))
            )
        )
        assert len({(f.ip_raw, f.source_field_locator) for f in observations}) < len(observations)
    engine.dispose()


def test_persistence_failure_rolls_back_observer(case_root):
    populated(case_root)
    calls = 0

    def fail(mapper, connection, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("SYNTHETIC_PRIVATE_PERSISTENCE_ERROR")

    event.listen(DeviceObservation, "before_insert", fail)
    try:
        assert observe_device_network(case_root).errors == 1
    finally:
        event.remove(DeviceObservation, "before_insert", fail)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        assert list(s.scalars(select(DeviceObservation))) == []
        assert list(s.scalars(select(NetworkObservation)))
        assert (
            s.scalars(select(ObservationRun).where(ObservationRun.observer_id == "device.observer"))
            .one()
            .status
            == "FAILED"
        )
    engine.dispose()
