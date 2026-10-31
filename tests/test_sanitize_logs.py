import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.sanitize_logs import redact_secrets


class TestSanitizeLogs(unittest.TestCase):
    def test_redact_bearer_token(self):
        log = "HTTP/1.1 200 OK\nAuthorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token\n"
        sanitized = redact_secrets(log)
        self.assertIn("Bearer <REDACTED>", sanitized)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI", sanitized)

    def test_redact_api_keys_and_passwords(self):
        log = "Connecting with api_key=abc12345xyz6789 and password='SuperSecretPassword123!'"
        sanitized = redact_secrets(log)
        self.assertIn("api_key=<REDACTED>", sanitized)
        self.assertIn("password=<REDACTED>", sanitized)
        self.assertNotIn("SuperSecretPassword123!", sanitized)

    def test_redact_github_pat(self):
        log = "Cloning with token ghp_A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8"
        sanitized = redact_secrets(log)
        self.assertIn("<REDACTED>", sanitized)
        self.assertNotIn("ghp_A1B2C3D4", sanitized)

    def test_redact_aws_and_punctuated_passwords(self):
        log = (
            "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
            "password=P@ssw0rd!123 "
            "passwd=admin1 "
            "aws_access_key_id=AKIAIOSFODNN7EXAMPLE"
        )
        sanitized = redact_secrets(log)
        self.assertIn("AWS_SECRET_ACCESS_KEY=<REDACTED>", sanitized)
        self.assertIn("password=<REDACTED>", sanitized)
        self.assertIn("passwd=<REDACTED>", sanitized)
        self.assertTrue("AKIA" not in sanitized or "<REDACTED>" in sanitized)
        self.assertNotIn("wJalrXUtnFEMI", sanitized)
        self.assertNotIn("P@ssw0rd!123", sanitized)
        self.assertNotIn("admin1", sanitized)

    def test_preserve_normal_logs(self):
        normal = "2026-10-03 07:00:00 [INFO] Processed 150 items in 0.42s with status=OK"
        self.assertEqual(redact_secrets(normal), normal)


def test_redact_bearer_token():
    TestSanitizeLogs().test_redact_bearer_token()

def test_redact_api_keys_and_passwords():
    TestSanitizeLogs().test_redact_api_keys_and_passwords()

def test_redact_github_pat():
    TestSanitizeLogs().test_redact_github_pat()

def test_redact_aws_and_punctuated_passwords():
    TestSanitizeLogs().test_redact_aws_and_punctuated_passwords()

def test_preserve_normal_logs():
    TestSanitizeLogs().test_preserve_normal_logs()


if __name__ == "__main__":
    unittest.main()
