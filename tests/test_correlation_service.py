import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import Engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.correlation.service import correlate_exact
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.parsing.service import parse_instagram
from evidence_engine.models.entities import (
    ArchiveMember,
    CorrelationCandidate,
    CorrelationRun,
    CorrelationSupport,
    DeviceObservation,
    EvidenceFile,
    NetworkObservation,
    ParsedRecord,
    SourceRecord,
)
from evidence_engine.observations.service import observe_device_network
from evidence_engine.storage.database import V4_TABLES, open_database


def seeded(root, count=3, archive=False):
    text = json.dumps(
        {
            "profile_account_insights": [
                {
                    "device_id": "SYNTHETIC-ID-001",
                    "ip_address": "203.0.113.10",
                    "timestamp": index * 1000000000,
                }
                for index in range(count)
            ]
        }
    )
    (root / "originals/profile_activity.json").write_text(text)
    if archive:
        with zipfile.ZipFile(root / "originals/synthetic.zip", "w") as z:
            z.writestr("profile_activity.json", text)
    ingest(root)
    assert parse_instagram(root).errors == 0
    assert observe_device_network(root).errors == 0


def snapshot(root, tables):
    with sqlite3.connect(root / "database/evidence.db") as c:
        return {t: c.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in tables}


def test_cli_idempotence_provenance_and_observation_only_inputs(case_root, monkeypatch):
    seeded(case_root, archive=True)
    before = snapshot(case_root, V4_TABLES)
    original_open = Path.open

    def no_evidence(path, *args, **kwargs):
        assert "originals" not in path.parts and "working" not in path.parts
        return original_open(path, *args, **kwargs)

    def no_earlier_inputs(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("select"):
            assert all(
                name not in statement.lower()
                for name in (
                    "parsed_records",
                    "normalized_events",
                    "source_records",
                    "archive_members",
                    "evidence_files",
                )
            )

    event.listen(Engine, "before_cursor_execute", no_earlier_inputs)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", no_evidence)
            result = CliRunner().invoke(app, ["correlate", "exact", "--case-root", str(case_root)])
    finally:
        event.remove(Engine, "before_cursor_execute", no_earlier_inputs)
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["candidates_created"] == 2 and summary["supports_created"] == 12
    assert summary["device_candidates"] == summary["network_candidates"] == 1
    assert all(isinstance(v, int) for v in summary.values())
    assert "SYNTHETIC" not in result.output and "203.0.113" not in result.output
    tables = ["correlation_candidates", "correlation_supports"]
    first = snapshot(case_root, tables)
    again = correlate_exact(case_root)
    assert again.candidates_created == again.supports_created == again.errors == 0
    assert again.candidates_existing == 2 and again.supports_existing == 12
    assert snapshot(case_root, tables) == first
    assert snapshot(case_root, V4_TABLES) == before
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        kinds = set()
        source_kinds = set()
        for support in s.scalars(select(CorrelationSupport)):
            candidate = s.get(CorrelationCandidate, support.candidate_id)
            model = (
                DeviceObservation if candidate.candidate_kind == "device" else NetworkObservation
            )
            observation = s.get(
                model, support.device_observation_id or support.network_observation_id
            )
            record = s.get(ParsedRecord, observation.parsed_record_id)
            source = s.get(SourceRecord, record.source_record_id)
            if source.archive_member_id:
                member = s.get(ArchiveMember, source.archive_member_id)
                evidence = s.get(EvidenceFile, member.evidence_file_id)
                source_kinds.add("archive")
            else:
                evidence = s.get(EvidenceFile, source.evidence_file_id)
                source_kinds.add("direct")
            assert (
                hashlib.sha256(
                    (case_root / "originals" / evidence.relative_path).read_bytes()
                ).hexdigest()
                == evidence.sha256
            )
            kinds.add(candidate.candidate_kind)
        assert kinds == {"device", "network"} and source_kinds == {"archive", "direct"}
    engine.dispose()


def test_large_group_persists_one_candidate_n_supports(case_root):
    seeded(case_root, count=259)
    result = correlate_exact(case_root)
    assert result.candidates_created == 2 and result.supports_created == 518
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        candidates = list(s.scalars(select(CorrelationCandidate)))
        assert all(c.support_count == 259 for c in candidates)
        for candidate in candidates:
            supports = list(
                s.scalars(
                    select(CorrelationSupport)
                    .where(CorrelationSupport.candidate_id == candidate.id)
                    .order_by(CorrelationSupport.support_ordinal)
                )
            )
            assert [x.support_ordinal for x in supports] == list(range(259))
    engine.dispose()


@pytest.mark.parametrize(
    "mutation", ["missing_support", "wrong_count", "wrong_ordinal", "vanished_group", "new_support"]
)
def test_support_divergence_never_rewrites_prior_results(case_root, mutation):
    seeded(case_root)
    assert correlate_exact(case_root).errors == 0
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        candidate = s.scalars(
            select(CorrelationCandidate).where(CorrelationCandidate.candidate_kind == "device")
        ).one()
        supports = list(
            s.scalars(
                select(CorrelationSupport).where(CorrelationSupport.candidate_id == candidate.id)
            )
        )
        if mutation == "missing_support":
            s.delete(supports[0])
        elif mutation == "wrong_count":
            candidate.support_count = 2
        elif mutation == "wrong_ordinal":
            supports[0].support_ordinal = 99
        elif mutation == "vanished_group":
            for index, o in enumerate(s.scalars(select(DeviceObservation))):
                o.value_raw = json.dumps(f"SYNTHETIC-UNIQUE-{index}")
        else:
            old = s.scalars(select(DeviceObservation)).first()
            values = {
                column.name: getattr(old, column.name)
                for column in DeviceObservation.__table__.columns
                if column.name not in {"id", "created_at"}
            }
            values["observation_ordinal"] = 1
            s.add(DeviceObservation(**values))
        s.commit()
    before = snapshot(case_root, ["correlation_candidates", "correlation_supports"])
    result = correlate_exact(case_root)
    assert result.errors == 1 and result.candidates_created == result.supports_created == 0
    assert snapshot(case_root, ["correlation_candidates", "correlation_supports"]) == before
    with Session(engine) as s:
        failed = s.scalars(select(CorrelationRun).where(CorrelationRun.status == "FAILED")).one()
        assert failed.error_code == "SUPPORT_SET_DIVERGENCE"
    engine.dispose()


@pytest.mark.parametrize("model", [CorrelationCandidate, CorrelationSupport])
def test_midrun_failure_rolls_back_all_new_rows(case_root, model):
    seeded(case_root)
    calls = 0

    def fail(mapper, connection, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("SYNTHETIC_PRIVATE_ERROR")

    event.listen(model, "before_insert", fail)
    try:
        assert correlate_exact(case_root).errors == 1
    finally:
        event.remove(model, "before_insert", fail)
    assert snapshot(case_root, ["correlation_candidates", "correlation_supports"]) == {
        "correlation_candidates": [],
        "correlation_supports": [],
    }
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        run = s.scalars(select(CorrelationRun)).one()
        assert run.status == "FAILED" and run.error_code == "CORRELATION_ERROR"
        assert (
            run.candidates_created == run.supports_created == 0
            and "PRIVATE" not in run.warnings_json
        )
    assert correlate_exact(case_root).errors == 0
    engine.dispose()


@pytest.mark.parametrize("durable", [False, True])
def test_uncertain_commit_preserves_durable_results(case_root, monkeypatch, durable):
    seeded(case_root)
    original_commit = Session.commit
    calls = 0

    def fail(session):
        nonlocal calls
        calls += 1
        if calls == 1:
            if durable:
                original_commit(session)
            raise OSError("synthetic commit failure")
        return original_commit(session)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail)
        if durable:
            with pytest.raises(EvidenceError, match="may already be durable"):
                correlate_exact(case_root)
        else:
            assert correlate_exact(case_root).errors == 1
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        run = s.scalars(select(CorrelationRun)).one()
        assert run.status == ("COMPLETED" if durable else "FAILED")
        assert run.error_code == (None if durable else "COMMIT_FAILED")
        assert len(list(s.scalars(select(CorrelationCandidate)))) == (2 if durable else 0)
    engine.dispose()


@pytest.mark.parametrize(
    "invalid", ["both", "neither", "cross_domain", "duplicate_observation", "duplicate_ordinal"]
)
def test_support_constraints(case_root, invalid):
    seeded(case_root)
    correlate_exact(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        candidate = s.scalars(
            select(CorrelationCandidate).where(CorrelationCandidate.candidate_kind == "device")
        ).one()
        device = s.scalars(select(DeviceObservation)).first()
        network = s.scalars(select(NetworkObservation)).first()
        values = dict(
            candidate_id=candidate.id,
            candidate_kind="device",
            support_ordinal=100,
            device_observation_id=None,
            network_observation_id=None,
        )
        if invalid == "both":
            values.update(device_observation_id=device.id, network_observation_id=network.id)
        elif invalid == "cross_domain":
            values.update(candidate_kind="network", network_observation_id=network.id)
        elif invalid == "duplicate_observation":
            values.update(device_observation_id=device.id)
        elif invalid == "duplicate_ordinal":
            values.update(support_ordinal=0, device_observation_id=device.id)
        s.add(CorrelationSupport(**values))
        with pytest.raises(IntegrityError):
            s.commit()
    engine.dispose()
