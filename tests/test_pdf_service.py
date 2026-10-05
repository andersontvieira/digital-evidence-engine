"""Synthetic operational probes; injected runtime checks are not deployment proof."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from evidence_engine.dossier import pdf_service as service
from evidence_engine.dossier import pdf_worker as worker
from evidence_engine.errors import EvidenceError
from tests.test_dossier_service import package_bytes
from tests.test_pdf_package import valid as valid
from tests.test_pdf_renderer import pytestmark as pytestmark

G1_SOURCE = "DEE_PDF_G1_SOURCE"
G1_OUTPUT_PARENT = "DEE_PDF_G1_OUTPUT_PARENT"


def records():
    return [
        asdict(worker.OutputRecord(path, 1, hashlib.sha256(b"x").hexdigest()))
        for path in worker.OUTPUT_PATHS
    ]


def supervise(tmp_path, monkeypatch, body, *, seconds=5, phase_seconds=120):
    monkeypatch.setattr(service, "PHASE_SECONDS", phase_seconds)
    prefix = (
        "import os,sys,time; from evidence_engine.dossier.pdf_worker import *; "
        "p=Peer(int(sys.argv[1]),int(sys.argv[2])); "
    )
    dropped = []
    result = service._supervise(
        lambda events, ack: [sys.executable, "-c", prefix + body, str(events), str(ack)],
        scratch=tmp_path,
        deadline=time.monotonic() + seconds,
        on_drop=lambda: dropped.append(True),
        monitor_scratch=lambda: None,
    )
    assert dropped == [True]
    return result


def test_complete_protocol_and_successful_exit(tmp_path, monkeypatch):
    body = (
        "\nfor event,phase in SEQUENCE: p.send(event,phase=phase)\np.send('READY',records="
        + repr(records())
        + ")"
    )
    result = supervise(tmp_path, monkeypatch, body)
    assert [asdict(row) for row in result] == records()


@pytest.mark.parametrize(
    "body,code",
    [
        ("os._exit(0)", "INTERNAL_ERROR"),
        ("os._exit(9)", "INTERNAL_ERROR"),
        ("os.kill(os.getpid(),9)", "INTERNAL_ERROR"),
        ("p.send('ENTER',phase='CAPTURE')", "INTERNAL_ERROR"),
        ("os.write(p.events_fd,b'{}\\n'); time.sleep(10)", "INTERNAL_ERROR"),
        ("os.write(p.events_fd,b'x'*4097); time.sleep(10)", "RESOURCE_LIMIT"),
        ("os.write(1,b'x'*65537); time.sleep(10)", "RESOURCE_LIMIT"),
        ("os.write(2,b'x'*65537); time.sleep(10)", "RESOURCE_LIMIT"),
        ("p.failure(MemoryError())", "RESOURCE_LIMIT"),
        ("p.failure(ValueError('private synthetic payload'))", "INTERNAL_ERROR"),
        (
            "import subprocess; "
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)']); "
            "time.sleep(10)",
            "INTERNAL_ERROR",
        ),
        (
            "import subprocess; "
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'], "
            "start_new_session=True); time.sleep(10)",
            "INTERNAL_ERROR",
        ),
    ],
)
def test_supervisor_abort_and_reap(tmp_path, monkeypatch, body, code):
    before = service._processes()
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_" + code + "$"):
        supervise(tmp_path, monkeypatch, body)
    after = service._processes()
    assert not {pid for pid, (parent, _) in after.items() if parent == os.getpid()} - before.keys()


def test_actual_hung_worker_global_deadline(tmp_path, monkeypatch):
    start = time.monotonic()
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        supervise(tmp_path, monkeypatch, "time.sleep(30)", seconds=0.4)
    assert time.monotonic() - start < 5


def test_actual_hung_render_phase_deadline(tmp_path, monkeypatch):
    body = "\nfor event,phase in SEQUENCE[:5]: p.send(event,phase=phase)\ntime.sleep(30)"
    start = time.monotonic()
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        supervise(tmp_path, monkeypatch, body, phase_seconds=0.15)
    assert time.monotonic() - start < 5


def test_event_channel_cumulative_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "CHANNEL_BYTES", 110)
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        supervise(tmp_path, monkeypatch, "\nfor event,phase in SEQUENCE: p.send(event,phase=phase)")


def test_worker_environment_is_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_SECRET", "must not inherit")
    env = service._worker_environment(tmp_path)
    assert "SYNTHETIC_SECRET" not in env and "HOME" not in env
    assert {env[key] for key in ("TMP", "TEMP", "TMPDIR")} == {str(tmp_path)}


def test_real_worker_d_binding_and_determinism(valid, tmp_path, monkeypatch):
    from evidence_engine.dossier import pdf_package

    monkeypatch.setattr(service, "_runtime_preflight", lambda *args: None)
    outputs = []
    for index in range(2):
        root = tmp_path / str(index)
        root.mkdir()
        source = root / "source"
        shutil.copytree(valid[0], source)
        before = package_bytes(source)
        destination = root / "published"
        result = service.export_dossier_pdf(source, destination)
        after = package_bytes(destination)
        assert set(after) == set(worker.OUTPUT_PATHS)
        assert result.file_count == 4 and result.total_byte_size == sum(map(len, after.values()))
        assert package_bytes(source) == before
        checked = pdf_package.verify_pdf_export(pdf_package.capture_source_package(source), after)
        assert dict(checked.files) == after
        outputs.append(after)
    assert outputs[0] == outputs[1]


@pytest.mark.skipif(
    G1_SOURCE not in os.environ or G1_OUTPUT_PARENT not in os.environ,
    reason="requires canonical G1 read-only source and writable output mounts",
)
def test_final_closure_real_cli_two_run_determinism():
    from evidence_engine.dossier import pdf_package

    source = Path(os.environ[G1_SOURCE])
    output_parent = Path(os.environ[G1_OUTPUT_PARENT])
    before = package_bytes(source)
    executable = shutil.which("dee")
    assert executable is not None
    outputs = []

    for label in ("run-a", "run-b"):
        destination = output_parent / label
        assert not destination.exists()
        result = subprocess.run(
            [
                executable,
                "dossier",
                "pdf",
                "--input-package",
                str(source),
                "--output-dir",
                str(destination),
            ],
            capture_output=True,
            check=False,
            timeout=service.GLOBAL_SECONDS + 30,
        )
        assert result.returncode == 0
        assert result.stdout == b"DOSSIER_PDF_OK\n"
        assert result.stderr == b""

        published = package_bytes(destination)
        assert set(published) == set(worker.OUTPUT_PATHS)
        captured = pdf_package.capture_source_package(source)
        checked = pdf_package.verify_pdf_export(captured, published)
        assert dict(checked.files) == published
        manifest = json.loads(published[pdf_package.MANIFEST_PATH])
        assert manifest["render_environment_id"] == checked.render_environment_id
        assert [entry["package_path"] for entry in manifest["entries"]] == [
            "human/consolidated-report.pdf",
            "human/dossier.pdf",
        ]
        assert package_bytes(source) == before
        outputs.append(published)

    assert outputs[0] == outputs[1]


def test_two_concurrent_exports_preserve_winner(valid, tmp_path):
    destination = tmp_path / "published"
    code = """
import sys
from pathlib import Path
from evidence_engine.dossier import pdf_service as s
s._runtime_preflight=lambda *args: None
try:
    s.export_dossier_pdf(Path(sys.argv[1]), Path(sys.argv[2]))
    print('OK')
except Exception as error:
    print(s.safe_error_code(error))
"""
    children = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(valid[0]), str(destination)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    results = [child.communicate(timeout=60) for child in children]
    assert sorted(out for out, _ in results) == [b"DOSSIER_PDF_OUTPUT_EXISTS\n", b"OK\n"]
    assert all(not err for _, err in results)
    assert set(package_bytes(destination)) == set(worker.OUTPUT_PATHS)


@pytest.mark.parametrize(
    "phase",
    ["CAPTURE", "RENDER_CONSOLIDATED", "VALIDATE_CONSOLIDATED", "RENDER_DOSSIER", "FINAL_RECHECK"],
)
def test_source_mutation_observed_by_original_capture(valid, tmp_path, phase):
    from evidence_engine.dossier import packaging

    source = tmp_path / "source"
    shutil.copytree(valid[0], source)
    stage = tmp_path / "stage"
    stage.mkdir()
    scratch = stage / "scratch"
    scratch.mkdir()
    mutated = False
    ready = []

    class Peer:
        def observe(self, event, current):
            nonlocal mutated
            if event == "ENTER" and current == phase and not mutated:
                path = source / "human/dossier.md"
                path.write_bytes(path.read_bytes() + b"\nsynthetic mutation\n")
                mutated = True
            if event == "ENTER" and current == "DROP_SCRATCH":
                scratch.rmdir()

        def send(self, event, **fields):
            ready.append(event)

    previous = os.getcwd()
    try:
        os.chdir(scratch)
        with pytest.raises(EvidenceError, match="DOSSIER_PDF_(INPUT_CHANGED|INTEGRITY_MISMATCH)"):
            worker.operation(source, stage, Peer())
    finally:
        os.chdir(previous)
    assert mutated and not ready
    packaging._inspect(source, directory=True)


def test_runtime_rejects_writable_input(valid, tmp_path):
    with pytest.raises(EvidenceError, match="ENVIRONMENT_UNSUPPORTED"):
        service._runtime_preflight(valid[0], tmp_path)


def test_startup_rlimit_failure_reaches_supervisor(tmp_path, monkeypatch):
    body = """
from evidence_engine.dossier import pdf_limits, pdf_worker
pdf_limits.impose_operation_worker_limits=lambda: pdf_limits.fail('ENVIRONMENT_UNSUPPORTED')
sys.argv=['pdf_worker','synthetic-input','synthetic-staging',sys.argv[1],sys.argv[2]]
sys.exit(pdf_worker.main())
"""
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_ENVIRONMENT_UNSUPPORTED$"):
        supervise(tmp_path, monkeypatch, body)


def test_same_process_service_is_non_reentrant(tmp_path, monkeypatch):
    def forbidden(*args):
        pytest.fail("second operation reached filesystem/runtime preflight")

    monkeypatch.setattr(service, "_prepare_paths", forbidden)
    with service._OPERATION_LOCK:
        with pytest.raises(EvidenceError, match="^DOSSIER_PDF_INTERNAL_ERROR$"):
            service.export_dossier_pdf(tmp_path / "source", tmp_path / "output")
    assert not service._OPERATION_LOCK.locked()
