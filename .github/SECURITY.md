# Security Policy

## Supported code

The current `main` branch is supported. A tagged release is supported until a newer release supersedes it.

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/goiltpatpat/patpat/security/advisories/new). Do not open a public issue for an unpatched vulnerability.

Include the affected host and version, installation route, impacted files or commands, minimal reproduction, expected security boundary, observed impact, and redacted evidence. Do not submit credentials, tokens, private repository contents, or personal data.

Security reports include unsafe delivery authority, install or update path traversal, state or evidence replay that can admit unverified work, secret disclosure, and bypass of explicit destructive-action gates. Use the bug template for ordinary functional defects.

Patpat coordinates local agents; local actor labels are not authentication. A same-user process that can rewrite repository or Git metadata remains inside the documented local trust boundary unless it crosses an explicit safety or delivery gate.
