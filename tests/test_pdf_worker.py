"""Synthetic phase observation and operational-worker isolation."""

import inspect
import subprocess
import sys

import pytest

from evidence_engine.dossier import pdf_limits as limits
from evidence_engine.dossier import pdf_package as package
from evidence_engine.dossier import pdf_renderer as renderer
from evidence_engine.errors import EvidenceError
from tests.test_pdf_model import document
from tests.test_pdf_package import valid as valid
from tests.test_pdf_renderer import pytestmark as pytestmark


def test_inert_boundary_without_observer(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("clock/process reached")

    import time

    monkeypatch.setattr(time, "monotonic", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with limits.phase_boundary("RENDER_DOSSIER"):
        pass
    with limits.phase_boundary(None):
        pass


def test_nested_boundaries_and_exception_restore():
    events = []
    other = []
    with limits.supervised_phases(lambda *event: events.append(event)):
        with pytest.raises(ValueError, match="synthetic"):
            with limits.phase_boundary("BIND"):
                with limits.phase_boundary("VALIDATE_CONSOLIDATED"):
                    raise ValueError("synthetic")
        with limits.supervised_phases(lambda *event: other.append(event)):
            with limits.phase_boundary("VALIDATE_DOSSIER"):
                pass
        with limits.phase_boundary("FINAL_RECHECK"):
            pass
    assert events == [
        ("ENTER", "BIND"),
        ("ENTER", "VALIDATE_CONSOLIDATED"),
        ("EXIT", "VALIDATE_CONSOLIDATED"),
        ("EXIT", "BIND"),
        ("ENTER", "FINAL_RECHECK"),
        ("EXIT", "FINAL_RECHECK"),
    ]
    assert other == [("ENTER", "VALIDATE_DOSSIER"), ("EXIT", "VALIDATE_DOSSIER")]
    with limits.phase_boundary("CAPTURE"):
        pass
    assert len(events) == 6


@pytest.mark.parametrize("kind", ["consolidated-report", "dossier"])
def test_renderer_observation_preserves_exact_bytes(kind):
    render = (
        renderer.render_dossier_pdf
        if kind == "dossier"
        else renderer.render_consolidated_report_pdf
    )
    content = document("Texto sintético.", kind)
    before = render(content)
    events = []
    with limits.supervised_phases(lambda *event: events.append(event)):
        actual = render(content)
    suffix = "DOSSIER" if kind == "dossier" else "CONSOLIDATED"
    assert events == [
        ("ENTER", "RENDER_" + suffix),
        ("EXIT", "RENDER_" + suffix),
        ("ENTER", "VALIDATE_" + suffix),
        ("EXIT", "VALIDATE_" + suffix),
    ]
    assert actual == before == render(content)
    assert len(events) == 4


def test_renderer_failure_exits_phase():
    events = []
    with limits.supervised_phases(lambda *event: events.append(event)):
        with pytest.raises(EvidenceError, match="UNSUPPORTED_MARKDOWN"):
            renderer.render_dossier_pdf(b"not a dossier")
    assert events == [("ENTER", "RENDER_DOSSIER"), ("EXIT", "RENDER_DOSSIER")]


def test_d_public_binding_api_unchanged():
    assert set(inspect.signature(package.bind_pdf_export).parameters) == {
        "source",
        "dossier_pdf",
        "consolidated_report_pdf",
    }
    assert set(inspect.signature(package.verify_pdf_export).parameters) == {"source", "files"}


def test_actual_d_nested_validations_are_observed(valid):
    source, result = valid[1:]
    events = []
    with limits.supervised_phases(lambda *event: events.append(event)):
        with limits.phase_boundary("VERIFY_STAGING"):
            assert package.verify_pdf_export(source, dict(result.files)) == result
    assert events == [
        ("ENTER", "VERIFY_STAGING"),
        ("ENTER", "VALIDATE_CONSOLIDATED"),
        ("EXIT", "VALIDATE_CONSOLIDATED"),
        ("ENTER", "VALIDATE_DOSSIER"),
        ("EXIT", "VALIDATE_DOSSIER"),
        ("EXIT", "VERIFY_STAGING"),
    ]


def test_observer_exception_does_not_leak_context():
    def rejected(*args):
        raise EvidenceError("DOSSIER_PDF_RESOURCE_LIMIT")

    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        with limits.supervised_phases(rejected):
            with limits.phase_boundary("CAPTURE"):
                pytest.fail("phase body reached after rejected ENTER")
    with limits.phase_boundary("CAPTURE"):
        pass


def test_operation_memory_helper_preserves_cpu_limit():
    code = (
        "import resource; "
        "from evidence_engine.dossier.pdf_limits import impose_operation_worker_limits; "
        "cpu = resource.getrlimit(resource.RLIMIT_CPU); "
        "impose_operation_worker_limits(); "
        "assert resource.getrlimit(resource.RLIMIT_AS) == (1024**3, 1024**3); "
        "assert resource.getrlimit(resource.RLIMIT_CPU) == cpu"
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=10)


@pytest.mark.parametrize(
    "data",
    [
        b'{"event":"ENTER","phase":"PREFLIGHT","seq":1,"v":1,"v":1}\n',
        b'{"event":"ENTER","phase":"PREFLIGHT","seq":true,"v":1}\n',
        b'{"event":"ENTER","phase":"PREFLIGHT","seq":1,"v":true}\n',
        b'{"event":"ENTER","phase":"OTHER","seq":1,"v":1}\n',
        b'{"event":"ACK","seq":1,"v":1}\n',
        b'{"event":"FAIL","code":"private","seq":1,"v":1}\n',
        b"{}\n\n",
        b"{}",
        b"[]\n",
        b"\xff\n",
        b"{}\r\n",
    ],
)
def test_protocol_rejects_noncanonical_or_open_shape(data):
    from evidence_engine.dossier.pdf_worker import decode

    with pytest.raises(EvidenceError, match="INTERNAL_ERROR"):
        decode(data)


def test_protocol_message_limit_and_ack_shape():
    from evidence_engine.dossier.pdf_worker import decode, encode

    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        decode(b"x" * 4097)
    message = {"event": "ACK", "seq": 1, "v": 1}
    assert decode(encode(message), ack=True) == message
    with pytest.raises(EvidenceError, match="INTERNAL_ERROR"):
        decode(encode({**message, "extra": 1}), ack=True)


def test_history_repetitions_late_exit_and_nested_deadlines():
    from evidence_engine.dossier.pdf_worker import SEQUENCE, History

    history = History(600)
    for seq, (event, phase) in enumerate(SEQUENCE, 1):
        history.accept({"v": 1, "seq": seq, "event": event, "phase": phase}, seq)
        assert history.phase_deadline == (
            seq + 120 if event == "ENTER" and phase.startswith(("RENDER_", "VALIDATE_")) else 600
        )
    history = History(600)
    for seq, (event, phase) in enumerate(SEQUENCE[:5], 1):
        history.accept({"v": 1, "seq": seq, "event": event, "phase": phase}, 0)
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        history.accept({"v": 1, "seq": 6, "event": "EXIT", "phase": "RENDER_CONSOLIDATED"}, 120)
    with pytest.raises(EvidenceError, match="INTERNAL_ERROR"):
        history.accept({"v": 1, "seq": 6, "event": "ENTER", "phase": "RENDER_CONSOLIDATED"}, 1)


def test_peer_rejects_ack_sequence_and_direction_caps(monkeypatch):
    from evidence_engine.dossier import pdf_worker as worker

    monkeypatch.setattr(worker.os, "write", lambda fd, data: len(data))
    monkeypatch.setattr(
        worker.os, "read", lambda fd, size: worker.encode({"v": 1, "seq": 2, "event": "ACK"})
    )
    with pytest.raises(EvidenceError, match="INTERNAL_ERROR"):
        worker.Peer(1, 2).send("ENTER", phase="PREFLIGHT")
    peer = worker.Peer(1, 2)
    peer.sent = worker.CHANNEL_BYTES
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        peer.send("ENTER", phase="PREFLIGHT")
    peer = worker.Peer(1, 2)
    peer.received = worker.CHANNEL_BYTES
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        peer.send("ENTER", phase="PREFLIGHT")
