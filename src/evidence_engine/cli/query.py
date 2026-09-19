"""Read-only current timeline with deterministic, restricted JSON output."""

import json
from dataclasses import asdict
from typing import Annotated

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError
from evidence_engine.query.incident import query_incident_window
from evidence_engine.query.incident_candidates import query_incident_candidates
from evidence_engine.query.provenance import query_provenance
from evidence_engine.query.search import query_device, query_network
from evidence_engine.query.timeline import query_timeline

app = typer.Typer(
    help="Read-only current events, exact technical search and persisted provenance.",
    no_args_is_help=True,
)


@app.command("incident-window")
def incident_window(
    case_root: CaseRoot,
    start: Annotated[str, typer.Option(help="Required inclusive UTC bound ending in Z.")],
    end: Annotated[str, typer.Option(help="Required exclusive UTC bound ending in Z.")],
    platform: Annotated[str | None, typer.Option(help="Exact platform filter.")] = None,
    event_kind: Annotated[str | None, typer.Option(help="Exact event kind filter.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=5000)] = 500,
) -> None:
    """Current events and same-ParsedRecord context; no temporal or identity inference."""
    try:
        result = query_incident_window(
            case_root,
            start=start,
            end=end,
            platform=platform,
            event_kind=event_kind,
            limit=limit,
        )
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


@app.command("incident-candidates")
def incident_candidates(
    case_root: CaseRoot,
    start: Annotated[str, typer.Option(help="Required inclusive UTC bound ending in Z.")],
    end: Annotated[str, typer.Option(help="Required exclusive UTC bound ending in Z.")],
    platform: Annotated[str | None, typer.Option(help="Exact event platform filter.")] = None,
    event_kind: Annotated[str | None, typer.Option(help="Exact event kind filter.")] = None,
    candidate_kind: Annotated[str | None, typer.Option(help="device or network.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 100,
) -> None:
    """Persisted candidates linked through same-record observations; counts are not scores."""
    try:
        result = query_incident_candidates(
            case_root,
            start=start,
            end=end,
            platform=platform,
            event_kind=event_kind,
            candidate_kind=candidate_kind,
            limit=limit,
        )
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


@app.command("timeline")
def timeline(
    case_root: CaseRoot,
    start: Annotated[str | None, typer.Option(help="Inclusive UTC bound ending in Z.")] = None,
    end: Annotated[str | None, typer.Option(help="Exclusive UTC bound ending in Z.")] = None,
    platform: Annotated[str | None, typer.Option(help="Exact platform filter.")] = None,
    event_kind: Annotated[str | None, typer.Option(help="Exact event kind filter.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=10000)] = 1000,
) -> None:
    """Return dated current events; undated counts obey platform/kind, not time bounds."""
    try:
        result = query_timeline(
            case_root, start=start, end=end, platform=platform, event_kind=event_kind, limit=limit
        )
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(result), ensure_ascii=True, sort_keys=True, separators=(",", ":")))


@app.command("device")
def device(
    case_root: CaseRoot,
    namespace: Annotated[str, typer.Option(help="Exact required namespace.")],
    value: Annotated[str, typer.Option(help="Literal string; no coercion or normalization.")],
    platform: Annotated[str | None, typer.Option()] = None,
    fact_kind: Annotated[str | None, typer.Option(help="identifier or model.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=10000)] = 100,
) -> None:
    """Search device.observer 1.0.0 without echoing the searched value."""
    try:
        result = query_device(
            case_root,
            namespace=namespace,
            value=value,
            platform=platform,
            fact_kind=fact_kind,
            limit=limit,
        )
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


@app.command("network")
def network(
    case_root: CaseRoot,
    ip: Annotated[str, typer.Option(help="IP address; input syntax canonicalized only.")],
    platform: Annotated[str | None, typer.Option()] = None,
    source_role: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=10000)] = 100,
) -> None:
    """Search network.observer 1.0.0 without echoing the IP."""
    try:
        result = query_network(
            case_root, ip=ip, platform=platform, source_role=source_role, limit=limit
        )
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


@app.command("provenance")
def provenance(
    case_root: CaseRoot,
    kind: Annotated[
        str,
        typer.Option(
            help="event, parsed-record, device-observation, network-observation, candidate."
        ),
    ],
    object_id: Annotated[str, typer.Option("--id", help="Exact object UUID.")],
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 100,
) -> None:
    """Follow persisted foreign keys to cataloged originals and hashes; never reread evidence."""
    try:
        result = query_provenance(case_root, kind=kind, object_id=object_id, limit=limit)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    if result is None:
        typer.echo('{"status":"NOT_FOUND"}')
        raise typer.Exit(2)
    typer.echo(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
