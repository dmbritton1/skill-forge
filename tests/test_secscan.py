"""Tests for the blocking secret scan (spec 11.1). Run: python3 tests/test_secscan.py"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from secscan import scan_text

SECSCAN = str(pathlib.Path(__file__).resolve().parent.parent / "scripts" / "secscan.py")


def rules_hit(text):
    return {rule for _, rule, _ in scan_text(text)}


def test_detects_aws_access_key():
    assert "aws-access-key" in rules_hit("key = AKIAIOSFODNN7EXAMPLE")


def test_detects_github_token():
    assert "github-token" in rules_hit("export GH=ghp_" + "a1B2" * 9 + "x")


def test_detects_stripe_live_key():
    assert "stripe-key" in rules_hit("stripe.api_key = sk_live_" + "a" * 24)


def test_detects_slack_token():
    assert "slack-token" in rules_hit("token: xoxb-123456789012-abcdefghij")


def test_detects_private_key_block():
    assert "private-key-block" in rules_hit("-----BEGIN RSA PRIVATE KEY-----")
    assert "private-key-block" in rules_hit("-----BEGIN OPENSSH PRIVATE KEY-----")


def test_detects_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
    assert "jwt" in rules_hit("Authorization: " + jwt)


def test_detects_bearer_token():
    assert "bearer-token" in rules_hit("curl -H 'Authorization: Bearer abcdef1234567890ABCDEF99'")


def test_detects_connection_string_with_password():
    assert "connection-string" in rules_hit("DATABASE_URL=postgres://admin:hunter2secret@db.internal:5432/app")


def test_detects_quoted_secret_assignment():
    assert "assigned-secret" in rules_hit('api_key = "9f8e7d6c5b4a3210ffff"')
    assert "assigned-secret" in rules_hit("password: 'correct-horse-battery'")


def test_detects_compound_name_secret_assignment():
    assert "assigned-secret" in rules_hit(
        'AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI7MDENGbPxRfiCY"')
    assert "assigned-secret" in rules_hit(
        "client_secret: '9f8e7d6c5b4a3210ffff'")
    assert "assigned-secret" in rules_hit('DB_PASSWORD="hunter2secret99"')
    assert "assigned-secret" in rules_hit('stripe_api_key = "9f8e7d6c5b4a3210ffff"')


def test_detects_provider_api_key_prefixes():
    assert "provider-api-key" in rules_hit("sk-ant-" + "a1B2" * 5)
    assert "provider-api-key" in rules_hit("sk-proj-" + "a1B2" * 5)
    assert "provider-api-key" in rules_hit("AIza" + "a1B2c3D4" * 3)
    assert "provider-api-key" in rules_hit("github_pat_" + "a1B2c3D4" * 3)


def test_reports_line_numbers():
    hits = scan_text("clean line\nkey = AKIAIOSFODNN7EXAMPLE\n")
    assert hits[0][0] == 2


def test_clean_skill_text_passes():
    clean = """---
name: stripe-webhook-integration
kind: skill
description: >
  Set up a Stripe webhook endpoint with signature verification.
  Do NOT use when consuming webhooks from other providers.
---
## Procedure
1. Mount `express.raw({type: 'application/json'})` BEFORE any json middleware.
2. Read the signing secret from the environment; never hardcode it.

## Gotchas
- Signature verification requires the raw request body.

## Verification
- `stripe trigger payment_intent.succeeded` should return 200 and log the event.
"""
    assert scan_text(clean) == []


def test_plain_urls_are_not_connection_strings():
    assert scan_text("See https://docs.stripe.com/webhooks for details.") == []


def test_unquoted_prose_about_secrets_passes():
    assert scan_text("Read the webhook signing secret from the Stripe dashboard.") == []


def test_main_missing_file_exits_2_without_traceback():
    result = subprocess.run(
        [sys.executable, SECSCAN, "/no/such/file/here.md"],
        capture_output=True, text=True)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "cannot read" in result.stderr


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS " + name)
            except AssertionError:
                failures += 1
                print("FAIL " + name)
    sys.exit(1 if failures else 0)
