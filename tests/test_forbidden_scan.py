"""The standalone repository scanner, both halves of it.

Defect D3 in the hostile review: half the scanner was inactive. `HASHED_DENY` shipped as an empty
frozenset, so the check that is supposed to catch a private name never ran at all, and the literal
deny list did the opposite of its job - it wrote several private path and directory names into the
one file whose whole purpose is to keep them out. A guard that lists what it forbids publishes what
it forbids.

The cure has two halves and this file tests both. Path SHAPES are regexes that name no machine, no
drive, no user and no directory. Private NAMES are one-way hashes generated from a token file that
lives outside this repository and is never copied into it.

Every path-shaped probe below is split so this test file does not itself contain the shape it is
testing for - the same trick the label-leak tests use.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Split so that this file, which the scanner also scans, does not itself carry the placeholder
# it is asserting about - the scan is not exempt from its own rules just because it is a test.
_PLACEHOLDER = "<copyright" + "_holder>"


def load_scanner():
    path = REPO_ROOT / "scripts" / "forbidden_scan.py"
    spec = importlib.util.spec_from_file_location("forbidden_scan_under_test_2", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scanner():
    return load_scanner()


# --- the hashed half must be switched on ------------------------------------------------------


def test_hashed_deny_is_populated(scanner) -> None:
    """Guards D3: this shipped as an empty frozenset, which made the scan announce a clean tree
    while the private-name check had never run. An empty set here means the guard is off."""
    assert len(scanner.HASHED_DENY) > 0
    assert all(len(h) == 64 and all(c in "0123456789abcdef" for c in h) for h in scanner.HASHED_DENY)


def test_hashed_deny_mechanism_actually_fires(scanner, tmp_path, monkeypatch) -> None:
    """Guards: a check that has never been shown to fail cannot certify a clean result. A sentinel
    word is hashed, injected as the deny set, and must be caught in a file - proving the mechanism
    rather than any particular private name, which is why no private name appears in this file."""
    sentinel = "zqxsentinelqzx"
    monkeypatch.setattr(
        scanner, "HASHED_DENY", frozenset({hashlib.sha256(sentinel.encode("utf-8")).hexdigest()})
    )
    hit = tmp_path / "note.md"
    hit.write_text(f"An ordinary sentence that happens to mention {sentinel} once.\n", encoding="utf-8")
    findings = scanner.scan_file(hit)
    assert any(f.startswith("HASHED_DENY:") for f in findings)


def test_a_hashed_finding_never_prints_the_word_that_produced_it(scanner, tmp_path, monkeypatch) -> None:
    """Guards the whole point of hashing: the report must not leak what the guard is guarding."""
    sentinel = "zqxsentinelqzx"
    monkeypatch.setattr(
        scanner, "HASHED_DENY", frozenset({hashlib.sha256(sentinel.encode("utf-8")).hexdigest()})
    )
    hit = tmp_path / "note.md"
    hit.write_text(sentinel, encoding="utf-8")
    findings = scanner.scan_file(hit)
    assert findings and all(sentinel not in f for f in findings)


def test_a_clean_file_produces_no_hashed_finding(scanner, tmp_path, monkeypatch) -> None:
    """Guards the other direction: the seeded positive above means nothing if everything hits."""
    monkeypatch.setattr(
        scanner, "HASHED_DENY", frozenset({hashlib.sha256(b"zqxsentinelqzx").hexdigest()})
    )
    clean = tmp_path / "clean.md"
    clean.write_text("Ordinary prose with nothing private in it at all.\n", encoding="utf-8")
    assert scanner.scan_file(clean) == []


def test_identifier_tokens_survive_the_split(scanner) -> None:
    """Guards the tokenizer change the hashed half depends on: a name written with an underscore
    must be deniable as one token, so that neither of the ordinary English words it is built from
    has to be denied on its own."""
    tokens = scanner.word_tokens("A path segment like one_two appears here.")
    assert "one_two" in tokens
    assert "one" in tokens and "two" in tokens


# --- the literal half must no longer be a list of private names --------------------------------


def test_literal_deny_holds_only_the_licence_placeholder(scanner) -> None:
    """Guards D3's other half: every private name that used to sit in this list is now a hash. The
    placeholder stays because it is not private and the message is useless without it."""
    assert scanner.LITERAL_DENY == (_PLACEHOLDER,)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("D:" + "/some/folder/file.txt", "drive_letter_root"),
        ("c:" + chr(92) + "some" + chr(92) + "folder", "drive_letter_root"),
        ("/us" + "ers/somebody/documents", "windows_user_home"),
        ("/ho" + "me/somebody/documents", "posix_user_home"),
    ],
)
def test_path_shapes_are_caught_as_shapes(scanner, tmp_path, text, expected) -> None:
    """Guards: the deny list was replaced by shapes, so the shapes had better still fire."""
    f = tmp_path / "note.md"
    f.write_text(text + "\n", encoding="utf-8")
    assert f"PATH_DENY:{expected}" in scanner.scan_file(f)


@pytest.mark.parametrize(
    "text",
    [
        "See https://example.invalid/docs for the reference.",
        "The ratio was written as 3:1 in the source.",
        "Use ftp://example.invalid/pub if the mirror is down.",
    ],
)
def test_ordinary_urls_and_ratios_are_not_mistaken_for_a_drive_root(scanner, tmp_path, text) -> None:
    """Guards the cure against over-firing: a one-letter drive root and a URL scheme end in the
    same two characters, so the rule needs the non-letter in front or every link in the README
    becomes a finding."""
    f = tmp_path / "note.md"
    f.write_text(text + "\n", encoding="utf-8")
    assert not any(x.startswith("PATH_DENY:") for x in scanner.scan_file(f))


# --- the personal-mailbox shape ------------------------------------------------------------------
#
# Every address below is assembled from fragments for the same reason every path probe above is:
# this file is scanned by the tree test at the bottom, and a probe written out whole would make
# the test file itself a finding.


@pytest.mark.parametrize(
    "text",
    [
        "somebody@" + "gma" + "il.com",
        "First.Last+tag@" + "outlo" + "ok.com",
        "someone@" + "prot" + "on.me",
    ],
)
def test_a_personal_mailbox_is_caught_as_a_shape(scanner, tmp_path, text) -> None:
    """Guards the gap the hashed half cannot close. The owner's private address cannot be denied
    by hashing its local part, because that local part is also the owner's public code-host
    handle, which the project metadata is entitled to carry. The shape rule catches the mailbox
    without anyone having to write the person's address into the guard."""
    f = tmp_path / "note.md"
    f.write_text(f"Contact: {text}\n", encoding="utf-8")
    assert "PATH_DENY:personal_mail_address" in scanner.scan_file(f)


@pytest.mark.parametrize(
    "text",
    [
        "someone-dev@" + "users.norep" + "ly.github.com",
        "The maintainer is reachable through the repository's issue tracker.",
        "See https://example.invalid/contact for how to get in touch.",
    ],
)
def test_a_public_no_reply_address_is_not_a_personal_mailbox(scanner, tmp_path, text) -> None:
    """Guards the other direction, which is the whole reason this rule is a shape and not a word:
    the public no-reply contact address must survive the scan, or the metadata this repository is
    published with becomes a finding of its own."""
    f = tmp_path / "note.md"
    f.write_text(f"Contact: {text}\n", encoding="utf-8")
    assert not any(x.startswith("PATH_DENY:") for x in scanner.scan_file(f))


# --- token-file handling ------------------------------------------------------------------------


def test_hash_tokens_file_skips_comments_and_blanks_and_sorts(scanner, tmp_path) -> None:
    """Guards regeneration: the same token file must produce a byte-identical block, or a diff of
    the committed hashes shows dictionary order instead of a real change."""
    token_file = tmp_path / "tokens.txt"
    token_file.write_text("# a note about where these came from\n\nBravo\nalpha\nalpha\n", encoding="utf-8")
    hashes = scanner.hash_tokens_file(token_file)
    assert hashes == sorted(
        {
            hashlib.sha256(b"bravo").hexdigest(),
            hashlib.sha256(b"alpha").hexdigest(),
        }
    )
    assert scanner.hash_tokens_file(token_file) == hashes


def test_hashed_deny_block_is_paste_ready(scanner) -> None:
    """Guards: the generated block is meant to be copied over the committed one unedited."""
    block = scanner.hashed_deny_block([hashlib.sha256(b"alpha").hexdigest()])
    assert block.startswith('        "') and block.rstrip().endswith('",')


# --- the tree itself -----------------------------------------------------------------------------


def test_the_shipped_tree_has_no_findings(scanner) -> None:
    """Guards the whole repository, both halves of the scan at once: no file in the shipped tree
    may carry a finding. The licence and the project metadata used to carry an unfilled
    copyright-holder placeholder as a deliberate refusal; the owner filled it at publication, and a
    tool must never write a legal name on the owner's behalf, so this test now pins the filled
    state while the placeholder tests above keep proving the scanner still catches an unfilled one."""
    findings = {}
    for path in scanner.iter_files(REPO_ROOT):
        hits = scanner.scan_file(path)
        if hits:
            findings[path.name] = hits
    assert findings == {}, findings
    for name in ("LICENSE", "pyproject.toml"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert _PLACEHOLDER not in text, name
