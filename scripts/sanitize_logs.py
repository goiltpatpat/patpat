#!/usr/bin/env python3
"""Sanitize sensitive credentials, tokens, and secrets from execution logs and command outputs."""

from __future__ import annotations

import re
import sys

# High-entropy tokens, auth headers, and common credential patterns
PATTERNS = [
    # Authorization: Bearer <token> or Basic <base64>
    (re.compile(r"((?:Bearer|Basic|token)\s+)[A-Za-z0-9_\-\.~+/]+=*", re.IGNORECASE), r"\1<REDACTED>"),
    # Common secret keys in key=value or key: value (quoted or unquoted, including punctuation and AWS secret keys)
    (
        re.compile(
            r"((?:(?:aws[_-]?)?secret[_-]?(?:access[_-]?)?key|api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|client[_-]?secret)\s*[:=]\s*)(?:'[^']*'|\"[^\"]*\"|[^\s,;'\"]{4,})",
            re.IGNORECASE,
        ),
        r"\1<REDACTED>",
    ),
    # GitHub personal access tokens
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,255}"), r"<REDACTED>"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{82}"), r"<REDACTED>"),
    # AWS Access Key ID
    (re.compile(r"(AKIA[0-9A-Z]{16})"), r"<REDACTED>"),
    # Private Key blocks
    (
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
        ),
        r"<REDACTED_PRIVATE_KEY>",
    ),
]


def redact_secrets(content: str) -> str:
    """Mask credentials and secrets within the provided text."""
    sanitized = content
    for pattern, replacement in PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def run_self_test() -> int:
    """Run built-in test assertions."""
    test_input = (
        "Auth: Bearer secret_token_123456\n"
        "api_key=my_super_secret_api_key_xyz\n"
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
        "password=P@ssw0rd!123\n"
        "passwd=admin1\n"
        "github_token: ghp_111122223333444455556666777788889999\n"
        "Normal line with no secrets: user=admin count=42"
    )
    output = redact_secrets(test_input)
    assert "<REDACTED>" in output, "Failed to redact secrets"
    assert "secret_token_123456" not in output, "Bearer token leaked"
    assert "my_super_secret_api_key_xyz" not in output, "API key leaked"
    assert "wJalrXUtnFEMI" not in output, "AWS secret access key leaked"
    assert "P@ssw0rd!123" not in output, "Punctuated password leaked"
    assert "admin1" not in output, "Short password leaked"
    assert "ghp_11112222" not in output, "GitHub PAT leaked"
    assert "Normal line with no secrets: user=admin count=42" in output, "Ordinary log corrupted"
    print("Sanitizer self-test passed successfully.")
    return 0


def main() -> int:
    """Stream stdin to stdout while masking secrets."""
    if len(sys.argv) > 1 and sys.argv[1] in ("--test", "--self-test"):
        return run_self_test()

    input_text = sys.stdin.read()
    sys.stdout.write(redact_secrets(input_text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
