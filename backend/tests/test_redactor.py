from app.runner import REDACTED, Redactor


def _stream(redactor: Redactor, chunks: list[str]) -> str:
    return "".join(redactor.feed(c) for c in chunks) + redactor.flush()


def test_passes_text_through_without_secrets() -> None:
    assert _stream(Redactor([]), ["hello ", "world"]) == "hello world"


def test_redacts_secret_within_a_chunk() -> None:
    assert _stream(Redactor(["hunter2"]), ["pw=hunter2!"]) == f"pw={REDACTED}!"


def test_redacts_secret_split_across_chunks() -> None:
    chunks = ["token: hun", "te", "r2 done"]
    assert _stream(Redactor(["hunter2"]), chunks) == f"token: {REDACTED} done"


def test_redacts_secret_split_one_character_at_a_time() -> None:
    text = "a hunter2 b hunter2"
    assert _stream(Redactor(["hunter2"]), list(text)) == f"a {REDACTED} b {REDACTED}"


def test_redacts_multiple_secrets_preferring_longest() -> None:
    redactor = Redactor(["abc", "abcdef"])
    assert _stream(redactor, ["x abcdef y abc z"]) == f"x {REDACTED} y {REDACTED} z"


def test_redacts_trimmed_value() -> None:
    assert _stream(Redactor(["  s3cret\n"]), ["value s3cret"]) == f"value {REDACTED}"


def test_streams_safe_prefix_immediately() -> None:
    redactor = Redactor(["hunter2"])
    # Everything except a possible secret prefix (6 chars) is released right away.
    assert redactor.feed("0123456789") == "0123"
    assert redactor.flush() == "456789"
