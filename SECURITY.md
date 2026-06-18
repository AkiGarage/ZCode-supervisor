# Security Policy

## Supported Versions

Security fixes are handled on the latest released version.

## Reporting

Do not open a public issue with secrets, credentials, or private logs. Open a
private advisory or contact the maintainers through the repository's configured
security contact.

## Scope

This project is a local supervisor and benchmark harness. It does not need
production credentials, cloud secrets, or private keys. Do not put secrets in
task packets, prompt files, screenshots, logs, or benchmark fixtures.

## Distribution

The primary package should be published through PyPI Trusted Publishing from the
public `AkiGarage/ZCode-supervisor` repository. Do not use long-lived PyPI API
tokens for release automation.

High-assurance users should verify GitHub Release archives with `SHA256SUMS` and
`gh attestation verify` before running setup from an archive.
