from codex_harbor.events import sanitize


def test_sanitizes_nested_secret_material():
    value = {
        "Authorization": "Bearer secret",
        "line": "api_key=abc password: xyz",
        "safe": ["cookie=qwerty"],
    }
    cleaned = sanitize(value)
    assert cleaned["Authorization"] == "[REDACTED]"
    rendered = str(cleaned)
    assert (
        "secret" not in rendered
        and "abc" not in rendered
        and "xyz" not in rendered
        and "qwerty" not in rendered
    )
