# Digital Evidence Engine

A reproducible Python data-processing engine for ingesting, normalizing, validating,
and correlating heterogeneous digital datasets while preserving provenance and producing
deterministic technical reports.

## Status and disclaimer

The project is an actively maintained beta-stage engineering portfolio. Its implemented
pipelines, safety boundaries, and deterministic outputs have extensive synthetic test and
qualification coverage. It is **not certified forensic software**, does not establish legal
admissibility, and does not infer human identity, authorship, intent, causality, or legal
conclusions.

**Real case evidence must never be committed to this repository.** Client data must also remain
outside it. The tracked fixtures are synthetic. Original inputs are treated as read-only;
databases, extracted working material, reports, and other derivatives belong in separate case
directories.

## What the engine does

Digital Evidence Engine provides a local, offline workflow that:

- inventories files and ZIP members with SHA-256 provenance;
- extracts supported Meta/Instagram, Google Takeout, and Apple export structures;
- normalizes supported observations into a versioned canonical event model;
- derives explicit device and network observations without inventing missing values;
- identifies exact-signal and temporal-proximity candidate groups;
- inventories media, exact duplicates, and perceptual image hashes;
- produces read-only timelines, incident views, provenance drill-downs, snapshots, and a
  consolidated technical report;
- assembles a deterministic dossier package and qualified PDF presentation on the supported
  Linux/amd64 path.

Every derived record retains a route to its parsed source and ultimately to the original file
or archive member and its SHA-256. Candidate correlation is kept distinct from identity or
authorship claims.

## Pipeline overview

```text
read-only originals
        |
        v
inventory + SHA-256 catalog -----> manifest / verification
        |
        v
versioned parsers -----> parsed records + precise source locators
        |
        v
canonical normalization -----> events + device/network observations
        |
        v
exact / temporal candidate generation + media analysis
        |
        v
read-only queries -----> snapshots -----> consolidated report
        |
        v
deterministic dossier package -----> Linux/amd64 PDF presentation
```

Writes are confined to case-owned database, working, and output areas. Processing failures are
fail-closed and preserve the last committed catalog baseline.

## Data Engineering concepts demonstrated

- **Heterogeneous ingestion:** regular files, bounded first-level ZIP extraction, JSON, HTML,
  CSV, and platform-specific export layouts.
- **ETL-style transformation:** explicit parse, normalize, observe, correlate, query, and report
  stages with versioned contracts.
- **Schema normalization:** a canonical SQLite model separates source records, parsed records,
  normalized events, observations, and candidate groups.
- **Idempotency:** successful work is reused by source identity and parser/normalizer version;
  equivalent observations from distinct sources remain distinct occurrences.
- **Data lineage:** derivations preserve source locators, container membership, file hashes, run
  identity, and implementation versions.
- **Data quality controls:** strict bounds, stable-file checks, schema validation, transactional
  rollback, deterministic ordering, and explicit unsupported/ambiguous states.
- **Deduplication without provenance loss:** exact content groups retain every source and
  occurrence rather than replacing them with a single representative.
- **Temporal normalization:** UTC is canonical only when source timezone information supports
  conversion; unresolved or ambiguous time remains explicit.
- **Deterministic output:** stable JSON, Markdown, package manifests, checksum files, and PDF
  bytes under the qualified environment.
- **Reproducible pipelines:** locked dependencies, synthetic fixtures, containerized validation,
  and platform-specific qualification boundaries.

## Core capabilities

| Area | Implemented capability |
| --- | --- |
| Evidence catalog | Read-only originals, SHA-256, ZIP safety limits, manifests, verification |
| Parsing | Supported Meta/Instagram JSON, Google HTML, and Apple CSV structures |
| Normalization | Versioned canonical events with original timestamp/timezone preservation |
| Observations | Explicit device identifiers, models, IP addresses, user-agent facts, and source labels |
| Correlation | Exact-value candidates, temporal-proximity candidates, and exact-signal overlap |
| Media | Inventory, exact duplicate sets, perceptual image hashes, and explicit source-media links |
| Query | Timeline, device/network search, provenance drill-down, and incident views |
| Reporting | Deterministic snapshots and consolidated Markdown technical report |
| Dossier | Explicit selection, 14-section human projection, integrity manifest, and checksums |
| PDF | Deterministic dossier/report presentation and no-replace publication on qualified Linux |

## Architecture and provenance model

The application uses layered Python modules over a per-case SQLite database. Parsers produce
source-linked observations; normalizers and correlation stages add derived records without
rewriting the original payload. Schema changes require explicit migrations, and the current
schema is version 5.

The semantic boundary is part of the data model:

- **OBSERVED:** directly present in a source;
- **DERIVED:** mechanically computed from supported inputs;
- **REPORTED:** supplied by a source but not independently established;
- **HYPOTHESIS:** an investigative proposition that cannot be promoted without new support.

See [Architecture](docs/architecture.md), [Evidence model](docs/evidence-model.md), and the
[architecture decision records](docs/adr/) for the full contracts and trade-offs.

## Installation

Requirements:

- Python 3.12;
- [uv](https://docs.astral.sh/uv/) 0.8.22 for the locked development workflow.

```bash
git clone https://github.com/andersontvieira/digital-evidence-engine.git
cd digital-evidence-engine
uv sync --locked --extra dev --python 3.12
uv run dee version
uv run dee --help
```

The project version remains pre-release while the public release candidate is prepared. Do not
place evidence or case working directories inside the clone.

## CLI quickstart

The CLI is organized by pipeline stage. These commands exist in the current implementation:

```bash
uv run dee evidence --help
uv run dee parse --help
uv run dee normalize --help
uv run dee observe --help
uv run dee correlate --help
uv run dee query --help
uv run dee media --help
uv run dee report --help
uv run dee dossier --help
```

For an approved case directory located outside the repository, a typical workflow is:

```bash
uv run dee evidence ingest --case-root /absolute/path/to/case
uv run dee evidence manifest --case-root /absolute/path/to/case
uv run dee evidence verify --case-root /absolute/path/to/case

uv run dee parse instagram --case-root /absolute/path/to/case
uv run dee parse google --case-root /absolute/path/to/case
uv run dee parse apple --case-root /absolute/path/to/case

uv run dee normalize events --case-root /absolute/path/to/case
uv run dee observe device-network --case-root /absolute/path/to/case
uv run dee correlate exact --case-root /absolute/path/to/case
uv run dee query timeline --case-root /absolute/path/to/case --limit 100
uv run dee media inventory --case-root /absolute/path/to/case
```

Report and dossier commands use explicit inputs and outputs. Inspect their help before use:

```bash
uv run dee report snapshot --help
uv run dee report consolidated --help
uv run dee dossier assemble --help
uv run dee dossier pdf --help
```

There is no packaged `dee demo` command yet. The planned public demo will use synthetic data
only.

## Docker support and platform boundary

The development container uses a digest-pinned Python base image, a locked uv environment, no
container network at runtime, and read-only source/original mounts. Copy `.env.example` to
`.env` and point all four case paths to directories **outside** the repository before using
Compose.

```bash
docker build -t digital-evidence-engine:dev .
docker run --rm --network none digital-evidence-engine:dev dee --help

docker compose run --rm dee dee evidence manifest
docker compose run --rm dee dee evidence verify
```

Core processing has Linux and native Windows coverage. Canonical PDF rendering and publication
are qualified only in the pinned Linux/amd64 environment, with a Linux-backed filesystem that
supports atomic no-replace publication. Windows may host that container; native Windows PDF
export is not qualified. One observed Windows-backed 9p/drvfs configuration returned `EINVAL`
for the required no-replace operation, which is not a claim about every 9p implementation.

## Testing and quality model

All parser and pipeline tests use synthetic fixtures. The normal development gates are:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

The repository also contains adversarial archive tests, transaction/rollback tests, Windows
path and identity tests, deterministic cross-process checks, PDF structural validation, and
PDFium visual-regression coverage. Some platform and PDF qualification gates require their
documented native or canonical container environment; skipped tests must not be reported as
passes.

Detailed PDF versions, environment identifiers, hashes, and qualification limits are recorded
in [PDF toolchain qualification](docs/pdf-toolchain-qualification.md).

## Safety and semantic boundaries

- Original files are read-only and are never silently replaced, renamed, or normalized.
- Real evidence, client identifiers, generated case reports, and case databases must not enter
  Git, fixtures, examples, logs, or release artifacts.
- Missing data remains missing; ambiguity is represented rather than silently resolved.
- Deduplication preserves every source and occurrence.
- Exact and temporal matches are candidates, not claims about identity, session, authorship,
  intent, or causality.
- The engine performs no upload, telemetry, cloud storage, external API call, or LLM analysis.
- WhatsApp is outside the represented dataset unless a separately approved acquisition and
  parser workflow is implemented.
- PDF output is not PDF/A or PDF/UA and carries no digital-signature or certification claim.
- Operational safeguards and deterministic output do not guarantee legal admissibility or a
  complete investigation.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and repository data-safety rules.

## Documentation index

- [Architecture](docs/architecture.md) — implemented layers, platform boundaries, and pipeline
  behavior.
- [Evidence model](docs/evidence-model.md) — schema v5 and provenance relationships.
- [Architecture decision records](docs/adr/) — accepted decisions from storage through dossier
  and PDF publication.
- [PDF toolchain qualification](docs/pdf-toolchain-qualification.md) — pinned renderer,
  validation environment, budgets, and synthetic qualification evidence.
- [Adversarial foundation audit](docs/adversarial-audit-milestone-1.md) — early ingestion and
  archive threat-model review.
- [Contribution guide](CONTRIBUTING.md) — development workflow and synthetic-fixture policy.
- [Security policy](SECURITY.md) — responsible disclosure and evidence-handling boundaries.

## Roadmap and intentionally deferred capabilities

The immediate release work covers public repository hygiene, a synthetic demonstration, CI,
and release-candidate packaging. The following capabilities are intentionally outside the
current product scope:

- WhatsApp acquisition or parsing;
- dashboard, FastAPI, Vue, or hosted service;
- AI/ML attribution, identity resolution, or authorship inference;
- geolocation enrichment or external intelligence services;
- additional platform parsers without an approved contract and synthetic fixtures;
- native Windows canonical PDF rendering;
- PDF/A, PDF/UA, signatures, certification, or guaranteed admissibility;
- automatic legal or investigative conclusions.

## License

Licensed under the [Apache License 2.0](LICENSE).
