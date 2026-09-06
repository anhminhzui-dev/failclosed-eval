#!/usr/bin/env python3
"""Standalone public-clean scanner for this repository.

Runs with no dependency on the failclosed_eval package or any third-party package, so CI's
forbidden-scan job can run it straight from a bare checkout, before any install step. It checks
every shipped file for three things:

1. LITERAL_DENY and PATH_DENY_RE - the unfilled licence placeholder, secret-bearing file
   suffixes, and private SHAPES written as regexes (a drive-letter root, a user-home directory,
   a personal mailbox at a consumer mail provider). No machine, drive, user, directory, person
   or private name is written out as a string.
2. HASHED_DENY   - sha256 hashes of forbidden *names* (an examination name, a rights-holder name,
   an internal codename, a private storage directory). The names themselves are never written in
   this file, not even inside the guard that bans them - only their hashes are compared. The set
   is generated with --hash-tokens from a token file kept outside the repository; were it ever
   empty, the scan announces that in its own output rather than printing a false "clean".
3. Value-carrying label leaks - the same two patterns failclosed_eval.validators uses to refuse a
   prompt at admission time, applied to every shipped file except fixtures/ (measurement data is
   the one quarantined exception) and any line carrying the anchor token below, so this file's own
   documentation of the pattern does not trip the pattern. LABEL-LEAK-DETECTOR-SOURCE
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Iterator, Sequence

SKIP_DIR_NAMES = {".git", "__pycache__", ".venv", "venv", "dist", "build", ".pytest_cache"}

# The only literal this file may hold is the licence placeholder, which is not a private name
# and has to be printable for the message to mean anything. Every private name - a storage or
# vault directory, an internal codename, an examination name, a rights holder - lives in
# HASHED_DENY below, and every private PATH SHAPE lives in PATH_DENY_RE as a shape, never as a
# name. A guard that lists what it forbids publishes what it forbids.
LITERAL_DENY: tuple[str, ...] = ("<copyright_holder>",)

# Private SHAPES, as regexes. None of these names a machine, a drive, a user, a directory or a
# person: each matches the SHAPE of something that must never appear in a published file. The
# drive-letter rule requires a non-letter in front so that a URL scheme ("http://") is not
# mistaken for a one-letter drive root.
PATH_DENY_RE: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("drive_letter_root", re.compile(r"(?<![a-z])[a-z]:[\\/]", re.IGNORECASE)),
    ("windows_user_home", re.compile(r"[\\/]users[\\/]", re.IGNORECASE)),
    ("posix_user_home", re.compile(r"[\\/]home[\\/][a-z0-9._-]+", re.IGNORECASE)),
    ("user_profile_variable", re.compile(r"%userprofile%|\$env:userprofile", re.IGNORECASE)),
    # A personal mailbox at a consumer mail provider, as a shape. This rule exists because the
    # hashed half below structurally cannot cover the owner's private address: the tokenizer
    # denies whole words only, and the local part of that address is the same handle as the
    # owner's public code-host account, which this project's metadata is entitled to carry.
    # Denying the handle would refuse the public no-reply contact address along with it. A shape
    # rule separates the two - it names no person, and a no-reply code-host domain is not a
    # consumer mail provider.
    (
        "personal_mail_address",
        re.compile(
            r"[a-z0-9._%+-]+@(?:gmail|googlemail|outlook|hotmail|live|yahoo|ymail|icloud|"
            r"aol|proton|protonmail|gmx|yandex|zoho|qq)\.[a-z]{2,}(?:\.[a-z]{2,})?",
            re.IGNORECASE,
        ),
    ),
)

# File-extension-shaped denials. A bare substring is too broad here: ".key" matches inside the
# ordinary Python method call ".keys()", and ".env" matches inside the ordinary English word
# ".environment" - both fired on this package's own test suite the first time this scanner ran.
# Each of these requires a trailing word boundary, so "id_rsa.key" still matches but "row.keys()"
# does not.
_EXTENSION_DENY: tuple[str, ...] = (".parquet", ".pem", ".key", ".env")
_EXTENSION_DENY_RE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(re.escape(ext) + r"\b", re.IGNORECASE) for ext in _EXTENSION_DENY
)

# Generated with --hash-tokens from a token file kept OUTSIDE this repository and never copied
# into it. Only these one-way hexes are committed; the words that produced them cannot be read back
# out of this file. Regenerate with:
#     python scripts/forbidden_scan.py --hash-tokens <path to the local token file>
# and paste the block it prints over this one. If the set is ever empty the scan says so out loud
# rather than letting a half-inactive check read as a clean result.
HASHED_DENY: frozenset[str] = frozenset(
    {
        "032cab5ebbc988153d81c3df611c39093b5fc531696753725173be03be0d8f18",
        "0661652820890613176da180316c4cdbe82aecc68cb8426f983d2c846d3f498e",
        "0c1eeccce6f114bf627c03a403d7c6e52e5b201ff1be893410a507066c9cc16b",
        "165f5e0d1d4cc3ea1e281af001e1a5998bd3f5eda2c27b913d7889c907c28306",
        "546f729f98eb03a0486f48ed2044711dfc9da79e1031a7c883c333bfb6d4e874",
        "57b003b3a857ddc804c7a66c5a27306ad653918cde9bd401251518ace61efee0",
        "656359bc1e55ae213165faf18fac5caa211123778c8695d15328b8d6de431c75",
        "659ab32d3107888aed862da1ad715088fed272e1ba4545fd6f89e0ce2624874a",
        "6d04f542b426bec69aee1f34b01588a14958749d34a1db894cc0f200f74ddf68",
        "6ff43db5339fb6aaee5417eac4a10c728799a9bf00d57901932a98b93bd87792",
        "810dc03c4810c8a4f8e7684ff5e78c4bc5266dc809aa8663b8c8f2066de4a092",
        "96cad2ff6e6e60a498323095e88ae16c36fa4c5be8a19e073d804bd66e64a0ba",
        "9bcd6d530324efd4c018d3ed5425ab2896e0b9e7f2d97710a47c31c92f9ce680",
        "b2908eb1ec9c11d0d47374b0ae0b22a5dab85ea61e46ac2510993d9a281565e5",
        "b6c4ac412ac8822355239dd717c11ca5b07373e4db550d0423c1b6aeceef8493",
        "b796b6acc1242a75189ffb38e0f1c051848f28cba25af3f165772f08e43c337f",
        "d972c62454deefd5d7cb8a0c39f5015daa6d4729ba5488a3d62236a5b9c06ade",
        "e15da43055a1b48f2e9370cf9ebf22c63ff41f4c50802a952af86243688f1f4b",
        "ea6c857a49a023ae5b36782ac18860305073eac6cc84fffa2fd80521f9ddbe8e",
        "eb2f62cd01d16c0aef15953fef2cf186b76a2f42535c426cfdd13dccb8d4c296",
        "ef68e7cb2f7463ef6e071792614149c1b228699ef09cd2b52956f10c4149f251",
        "fbe96c8edfbfe0d97d9b4074fb1d8aec7bcd4c13c44f5291d7db0c7b637730eb",
    }
)

LEAK_EXEMPT_ANCHOR = "LABEL-LEAK-DETECTOR-SOURCE"
_LABEL_WORDS = ("level", "score", "rating", "grade", "mark", "band")
# No leading \b on purpose: "_" is a word character, so \b fails exactly where a leak hides, inside
# an identifier. The separator class is repeated, not a single optional character, because a JSON
# form (quote, colon, space) slips through a single optional separator. Only a value-carrying match
# counts - a bare label word is never a hit. LABEL-LEAK-DETECTOR-SOURCE
LABEL_LEAK_RE: re.Pattern[str] = re.compile(
    r"(?<![a-z])(?:" + "|".join(_LABEL_WORDS) + r")[ _\"'-]*[:=]?[ \"']*[-+]?\d+(?:\.\d+)?",
    re.IGNORECASE,
)
VERDICT_LEAK_RE: re.Pattern[str] = re.compile(r"(?:UN)?MET[ _\"'-]*[:=][ \"']*\S", re.IGNORECASE)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Identifiers are tokens too. Splitting on every non-alphanumeric character would break a
# private directory name that carries an underscore into two ordinary English words, and
# hashing either half on its own would fire on innocent prose. Both shapes are emitted, so an
# underscored name can be denied whole without denying its parts.
_IDENT_RE = re.compile(r"[a-z0-9_]+")


def iter_files(root: Path) -> Iterator[Path]:
    """Yield every regular file under root, skipping build/VCS directories and this script."""
    try:
        self_path: Path | None = Path(__file__).resolve()
    except OSError:
        self_path = None
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if self_path is not None:
            try:
                if path.resolve() == self_path:
                    continue
            except OSError:
                pass
        yield path


def word_tokens(text: str) -> set[str]:
    """Lower-case tokens in two shapes: alphanumeric runs, and identifier runs that keep their
    underscores. A name written `one_two` is therefore denied as `one_two` without `one` or `two`
    ever having to be denied on their own."""
    lowered = text.lower()
    return set(_TOKEN_RE.findall(lowered)) | set(_IDENT_RE.findall(lowered))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_fixture_path(path: Path) -> bool:
    return "fixtures" in path.parts


def scan_file(path: Path) -> list[str]:
    """Return one finding string per hit; an empty list means the file is clean."""
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return []  # unreadable or binary files carry no text evidence to scan

    findings: list[str] = []
    lowered = text.lower()

    for literal in LITERAL_DENY:
        if literal in lowered:
            findings.append(f"LITERAL_DENY:{literal}")

    for name, pattern in PATH_DENY_RE:
        if pattern.search(text):
            findings.append(f"PATH_DENY:{name}")

    for ext, pattern in zip(_EXTENSION_DENY, _EXTENSION_DENY_RE):
        if pattern.search(text):
            findings.append(f"LITERAL_DENY:{ext}")

    if HASHED_DENY:
        for token in word_tokens(text):
            digest = hash_token(token)
            if digest in HASHED_DENY:
                # Print the hash prefix only, never the plaintext token that produced it.
                findings.append(f"HASHED_DENY:{digest[:12]}")

    if not _is_fixture_path(path):
        for line in text.splitlines():
            if LEAK_EXEMPT_ANCHOR in line:
                continue
            hits = len(LABEL_LEAK_RE.findall(line)) + len(VERDICT_LEAK_RE.findall(line))
            if hits:
                findings.append(f"VALUE_LABEL_LEAK:{hits}")

    return findings


def hash_tokens_file(path: Path) -> list[str]:
    """sha256 hex of each non-blank, non-comment line of a local, one-word-per-line token file.

    Sorted, so regenerating from the same token file produces a byte-identical block and a diff
    shows a real change rather than dictionary order. Blank lines and '#' lines are skipped so the
    local file can carry a note about where its words came from.
    """
    hashes: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        word = raw_line.strip().lower()
        if not word or word.startswith("#"):
            continue
        hashes.add(hash_token(word))
    return sorted(hashes)


def hashed_deny_block(hashes: list[str]) -> str:
    """The paste-ready body of HASHED_DENY: one quoted hex per line, eight spaces of indent, so
    regeneration is a copy, not a hand edit."""
    return "\n".join(f'        "{h}",' for h in hashes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forbidden_scan.py",
        description="Public-clean scan: literal paths, hashed forbidden names, value-carrying labels.",
    )
    parser.add_argument("--root", default=".", help="Repository root to scan (default: .).")
    parser.add_argument(
        "--hash-tokens",
        default=None,
        metavar="PATH",
        help="Path to a local, gitignored, one-word-per-line file; print each line's sha256 hex "
        "(for building HASHED_DENY) and exit without scanning.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse's own exit codes (0 for --help, 2 for a parse error) collapse to this script's
        # "bad usage" code, except a genuine --help stays 0.
        return 0 if exc.code in (0, None) else 1

    if args.hash_tokens is not None:
        token_path = Path(args.hash_tokens)
        if not token_path.is_file():
            print(f"ERROR: token file not found: {token_path}", file=sys.stderr)
            return 1
        hashes = hash_tokens_file(token_path)
        # Printed as the exact block that belongs in HASHED_DENY above. The token file itself is
        # never read by the scan and never lives in this repository; only this output does.
        print("HASHED_DENY: frozenset[str] = frozenset(")
        print("    {")
        print(hashed_deny_block(hashes))
        print("    }")
        print(")")
        print(f"# {len(hashes)} token(s) hashed", file=sys.stderr)
        return 0

    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: --root is not a directory: {root}", file=sys.stderr)
        return 1

    hit_files = 0
    for path in sorted(iter_files(root)):
        findings = scan_file(path)
        if findings:
            hit_files += 1
            try:
                rel = path.resolve().relative_to(root.resolve())
            except ValueError:
                rel = path
            # Name the finding kinds, not just a count: a reader must be able to tell an
            # unfilled licence placeholder from a leaked absolute path without opening the file.
            # A hashed hit prints its hash prefix only, never the plaintext that produced it.
            kinds = ",".join(sorted(set(findings)))
            print(f"{rel.as_posix()}={len(findings)} [{kinds}]")

    if not HASHED_DENY:
        print(
            "NOTE: HASHED_DENY is empty - the hashed forbidden-name check is INACTIVE. "
            "Generate it with --hash-tokens before treating a clean result as complete."
        )

    if hit_files:
        print(f"SCAN: {hit_files} file(s) with findings")
        return 2

    print("SCAN: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
