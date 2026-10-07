# Changelog

## 0.7.1 - Unreleased

### Fixed

- Portable Agent Plugins staging now emits Agent Skills-compatible frontmatter for all 26 skills. Codex's native invocation gates remain intact; the portable projection carries an explicit-request instruction that clients do not enforce.

### Changed

- Bump the shared Codex and Cursor package version to `0.7.1`; generated Agent Plugins inherit this version so clients can detect the package correction.
