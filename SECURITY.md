# Security Policy

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this repository if it is
available. If it is not enabled, open a minimal public issue asking the maintainer to establish
a private reporting channel. Do not include exploit details, secrets, personal data, evidence,
client identifiers, or local filesystem paths in a public issue.

Allow the maintainer reasonable time to reproduce and address a report before public disclosure.
Include only synthetic reproduction material and the minimum technical detail needed to locate
the affected version and boundary.

## Evidence and secret handling

Never commit or attach:

- real evidence or material derived from a real case;
- client names, identifiers, messages, media, reports, or case metadata;
- case databases, manifests, checksums, exports, or generated PDFs;
- credentials, tokens, private keys, environment files, or machine-specific paths.

If sensitive material is exposed, stop distributing it, preserve only the minimum information
needed for incident handling, and contact the repository maintainer through a private channel.
Repository ignore rules do not protect content that was already tracked or forcibly added.

## Security boundary

The engine is designed for local, offline processing. It does not require telemetry, upload,
cloud storage, external APIs, or LLM services. Original evidence is expected to be mounted or
opened read-only, while databases, extracted working files, and outputs use separate case-owned
directories outside the repository.

Security controls, provenance checks, deterministic output, and fail-closed resource limits do
not constitute forensic certification, guaranteed legal admissibility, or protection against a
compromised host.
