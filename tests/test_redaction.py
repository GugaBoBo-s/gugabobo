from gugabobo.infra.redaction import redact_sensitive


def test_redaction_covers_tokens_and_url_credentials():
    text = (
        "https://user:password@proxy.example "
        "github_pat_abcdefghijklmnopqrstuvwxyz123456 "
        "Bearer abcdefghijklmnopqrstuvwxyz123456"
    )

    redacted = redact_sensitive(text)

    assert "password" not in redacted
    assert "github_pat_" not in redacted
    assert "Bearer abc" not in redacted
    assert redacted.count("<redacted>") == 3
