"""Guards CONTRACT.md section 4 (provenance.py): canonical hashing is key-order independent,
the empty-string digest is pinned, every hash is 64-char lowercase hex, unit_id has the pinned
shape, and file_hash agrees with text_hash on the bytes it streams."""
from __future__ import annotations

import string

from failclosed_eval import canonical_hash, file_hash, text_hash, unit_id


def test_canonical_hash_is_key_order_independent() -> None:
    """Guards: canonical_hash sorts keys before hashing, so {"a":1,"b":2} == {"b":2,"a":1}."""
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_text_hash_empty_string_matches_pinned_digest() -> None:
    """Guards: text_hash("") is the well-known sha256 of the empty byte string, exactly."""
    assert text_hash("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_canonical_hash_of_empty_object_is_64_char_lowercase_hex() -> None:
    """Guards: canonical_hash always returns a 64-character lowercase hex digest."""
    digest = canonical_hash({})
    assert len(digest) == 64
    assert all(c in string.hexdigits.lower() for c in digest)
    assert digest == digest.lower()


def test_unit_id_shape() -> None:
    """Guards: unit_id joins item_id and an upper-cased criterion with '::', exactly."""
    assert unit_id("x-1", "clarity") == "x-1::CLARITY"


def test_file_hash_equals_text_hash_for_ascii_file(tmp_path) -> None:
    """Guards: file_hash streams the file in chunks but must agree with text_hash on the same
    bytes read directly - the streaming path must not silently diverge from the reference path.
    Written with write_bytes (not write_text) so no platform newline translation can put a
    different byte sequence on disk than the string this test compares against - on Windows,
    Path.write_text translates "\\n" to "\\r\\n", which would make this comparison spuriously
    fail for a reason that has nothing to do with file_hash itself."""
    content = "hello failclosed-eval\n"
    p = tmp_path / "sample.txt"
    p.write_bytes(content.encode("ascii"))
    assert file_hash(p) == text_hash(content)
