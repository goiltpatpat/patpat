import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.sanitize_logs import redact_secrets


def test_redact_bearer_token():
    log = "HTTP/1.1 200 OK\nAuthorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token\n"
    sanitized = redact_secrets(log)
    assert "Bearer <REDACTED>" in sanitized
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI" not in sanitized


def test_redact_api_keys_and_passwords():
    log = "Connecting with api_key=abc12345xyz6789 and password='SuperSecretPassword123!'"
    sanitized = redact_secrets(log)
    assert "api_key=<REDACTED>" in sanitized
    assert "password=<REDACTED>" in sanitized
    assert "SuperSecretPassword123!" not in sanitized


def test_redact_github_pat():
    log = "Cloning with token ghp_A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8"
    sanitized = redact_secrets(log)
    assert "<REDACTED>" in sanitized
    assert "ghp_A1B2C3D4" not in sanitized


def test_redact_aws_and_punctuated_passwords():
    log = (
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
        "password=P@ssw0rd!123 "
        "passwd=admin1 "
        "aws_access_key_id=AKIAIOSFODNN7EXAMPLE"
    )
    sanitized = redact_secrets(log)
    assert "AWS_SECRET_ACCESS_KEY=<REDACTED>" in sanitized
    assert "password=<REDACTED>" in sanitized
    assert "passwd=<REDACTED>" in sanitized
    assert "AKIA" not in sanitized or "<REDACTED>" in sanitized
    assert "wJalrXUtnFEMI" not in sanitized
    assert "P@ssw0rd!123" not in sanitized
    assert "admin1" not in sanitized


def test_preserve_normal_logs():
    normal = "2026-10-03 07:00:00 [INFO] Processed 150 items in 0.42s with status=OK"
    assert redact_secrets(normal) == normal


if __name__ == "__main__":
    test_redact_bearer_token()
    test_redact_api_keys_and_passwords()
    test_redact_github_pat()
    test_redact_aws_and_punctuated_passwords()
    test_preserve_normal_logs()
    print("All sanitize_logs unit tests passed.")
