from subagg.sources.remote import redact_url


def test_remote_url_redaction_preserves_path_and_hides_query_values():
    value = redact_url("https://example.com/sub?token=secret&key=another")
    assert value == "https://example.com/sub?token=%3Credacted%3E&key=%3Credacted%3E"
    assert "secret" not in value
    assert "another" not in value
