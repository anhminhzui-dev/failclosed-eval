# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-06

### Added

- Tier-1 unit refusal: a unit is counted, named in the trace, and excluded; any refusal forces
  the run verdict to `HOLD`. Codes: `INPUT_IMAGE_REQUIRED`, `MISSING_INSTRUCTION`,
  `UNRESOLVED_IMAGE`, `INVALID_IMAGE_PAYLOAD`, `LABEL_LEAK_IN_PROMPT`, `IMAGE_SLOT_MISSING`.
- Tier-2 run halt: the whole run stops immediately and writes `halt.json`. Codes:
  `NOT_SYNTHETIC`, `MALFORMED_UNITS_FILE`, `EMPTY_UNITS_FILE`, `MISSING_POLICY_FIELD`,
  `INVALID_POLICY`, `MISSING_ITEM_ID`, `UNKNOWN_CRITERION`, `UNKNOWN_ITEM_TYPE`,
  `DUPLICATE_UNIT`, `MISSING_COMPONENT_EVIDENCE`, `INVALID_WEIGHT`, `INVALID_ESTIMATE_VALUE`,
  `ANOMALOUS_ESTIMATE`, `ANOMALOUS_DISTRIBUTION`, `MISSING_DENOMINATOR`.
- Mandatory image slot in every built payload, present even when empty, so a caller cannot
  forget it — it can only be refused.
- Public-clean guard: every input row must carry `"synthetic": true` or the run halts
  (`NOT_SYNTHETIC`), unless the operator explicitly passes `--allow-nonsynthetic`.
- Abstain layer: two or more independent estimates that disagree (spread or population
  standard deviation over threshold) abstain instead of committing a value; one estimate always
  commits; zero estimates abstains.
- Anomaly halt: a value at the policy floor paired with high component evidence, or one value
  holding more than the configured share of a criterion's rows, halts the run.
- Per-unit provenance: a canonical, key-order-independent SHA-256 over the whole payload, plus
  an image SHA-256 or `null`. The trace file carries these hashes and nothing else — no
  estimate, reference, component, or weight value is ever written to `trace.jsonl`.
- Denominator line that names every exclusion class out loud, per criterion, so no count is
  ever printed without saying what it is out of.
- Default-`HOLD` verdict rule: `GO` requires no halt, zero refusals, and every criterion with a
  positive denominator; anything else, including an unhandled exception at the CLI boundary,
  reports `HOLD`.
- `failclosed-eval` CLI with `run`, `scan`, and `version` subcommands.
- Label-leak scanner (value-carrying patterns only; a bare label word is never a hit) used both at
  admission time and as a standalone repository scan (`scripts/forbidden_scan.py`), each with a
  documented exemption anchor so the scanner does not trip on the text that explains it. Measured
  rather than asserted: over `fixtures/fp_corpus_instructions.txt`, 250 invented instruction lines
  that all legitimately carry a label word with a digit, 4 lines fire — 1.60%. All four are the
  same declared shape, a standalone label word with a digit welded to it, which is structurally
  identical to a real leak. A value spelled in words is out of scope and is pinned as such.
- Optional MLflow tracking (`tracking.py`): a no-op `NullTracker` by default; when enabled and
  MLflow is importable, logs validity counts, hashes, and the verdict only — never a measured
  value. The package imports and runs with MLflow absent.
- Synthetic fixture set (`fixtures/`) covering one clean run and one single-defect fixture per
  gate, so every gate has a demonstrated pass and a demonstrated, seeded failure.
- Deterministic fixture generator (`scripts/make_fixtures.py`): N synthetic units across all four
  criteria with stated shares of seeded-bad, abstaining and reference-free rows; stdlib only, same
  seed reproduces the same bytes, `--verify` proves it before writing. Output is gitignored — the
  command is committed, not the rows. Recorded run at 2,000 units: 1,800 admitted, 100 refused
  (34 / 33 / 33 across the three refusal codes), 60 abstained, 40 excluded for a missing reference,
  2,000 trace rows, `HOLD (refused units)` at exit 2, 0.17 s wall clock.
- CI (`.github/workflows/ci.yml`): pytest across three Python versions, the forbidden-content
  scan, and a must-refuse job that proves both a clean run (exit 0, `VERDICT: GO`) and a seeded
  bad run (exit 2, refusal code present in the written summary).

### Fixed

- A malformed element inside `estimates` escaped the typed refusal system and surfaced as an
  unnamed `UNEXPECTED_ERROR` at exit 1. The estimates list is now validated before the abstain
  rule sees it and halts with the documented `INVALID_ESTIMATE_VALUE` at exit 2, with a seeded-bad
  fixture and tests beside the other seven gates.
- The label-leak pattern had no assertion in front of the label word, so ordinary English words
  ending in one of them (a benchmark year, a landmark number, an upgrade release) were refused as
  leaks. A non-letter lookbehind, applied identically to both copies of the pattern, cuts the
  measured false-positive rate over the new corpus from 34.80% to 1.60%; an underscore is still not
  a letter, so a leak hiding inside an identifier still fires.
- A halted run printed counts that looked complete and never said where it stopped. The
  denominators are now marked `PARTIAL` on a halt and the halting unit id is printed on stdout.
- The denominator report is one row per criterion instead of a single line that wrapped into an
  unreadable block.
- The repository scan's hashed forbidden-name half shipped empty and therefore inactive; it is now
  generated and live. Its literal deny list, which had written several private path and directory
  names into the one file meant to keep them out, is gone: path shapes are regexes that name
  nothing, and private names exist only as one-way hashes.
- `reference` is documented in code and in the README as a deliberate boundary — collected,
  validated, and never used for any accuracy figure — with a test that walks every written file and
  fails if a number appears under any key that is not a declared count.
- `count_label_leaks` honoured its own documentation-exemption anchor unconditionally, so the
  same skip that legitimately lets the README explain a leak example without refusing itself also
  let an untrusted instruction switch the admission-time refusal off by pasting that anchor onto a
  real leak — the run returned `VERDICT: GO` with zero refusals. `count_label_leaks` now takes
  `honour_exemption: bool = False`; only `scan_paths_for_leaks` (the repository-scanning path)
  passes `True`, and the admission path (`scan_text_for_leaks`, used by `build_payload`) never
  does.
- Every CLI command block in the README omitted `PYTHONPATH=src`, so the first command a reviewer
  copy-pasted failed with `ModuleNotFoundError`. A "Run it" section now states the prefix (and its
  PowerShell / `cmd.exe` equivalents) before the first example, and every command block carries it
  inline.

### Changed

- Licence replaced. The package was drafted under MIT, which permits redistribution, derivative
  works and commercial use - the opposite of what this repository is for. It now ships a short
  plain-English **Evaluation-Only Licence 1.0**: reading, cloning and running it to evaluate the
  author's work is permitted; redistribution, modification for distribution, derivative works,
  incorporation into another product, model or dataset, and commercial use are reserved. A
  standard licence was checked first and rejected on its own text - PolyForm Strict 1.0.0 grants
  its copyright licence for any permitted purpose and defines any noncommercial purpose as
  permitted, which is far broader than an evaluation-only grant. `pyproject.toml` carries the
  matching metadata, an `Other/Proprietary License` classifier, and a deliberately invalid
  `Private :: Do Not Upload` classifier so a public package index rejects an upload.
- Authorship metadata added, and deliberately impersonal: the author name is the same unfilled
  copyright-holder placeholder the licence carries (the token itself is not written out here -
  this file is scanned too, and a document that quotes it becomes a finding of its own), and the
  contact address is a public code-host no-reply address. No personal mailbox appears anywhere in
  this tree.
- The repository's own scan therefore refuses **two** files on a fresh checkout rather than one -
  the licence and the project metadata - each for the same unfilled copyright-holder placeholder.
  Both refusals are deliberate; filling in a legal name is the owner's step, not a tool's.

### Security

- Leak audit over every shipped file. No absolute local path, machine name, user name, personal
  mailbox, telephone number, customer name or private measurement value was found in the tree;
  the residual statements about the private system this package was extracted from are catalogued
  in the audit report that accompanies this build, each marked keep or cut for the owner.
- Four references to the private system's own governance file by name, and three uses of that
  system's internal vocabulary for itself, were removed from source and test docstrings. The
  substance of each lesson is kept; only the private file name and the internal word are gone.
- Hashed deny list widened from 12 tokens to 22: the storage and vault names, the private
  codenames, the examination name, the rights holders, the design-partner and prospect names, and
  the demo institution name. As before, only the one-way hashes are committed - the token file
  that produces them lives outside this repository and is never copied into it.
- New private-shape rule, `personal_mail_address`: a mailbox at a consumer mail provider is
  refused as a shape. This closes a gap the hashed half structurally cannot: the owner's private
  address and the owner's public code-host handle share a local part, so denying the word would
  refuse the public no-reply contact address as well. Both directions are tested - a consumer
  mailbox must fire, the no-reply address must not.

### Notes

- This is an extraction of a private system's measurement harness onto synthetic data. It
  demonstrates the measurement design. No accuracy is claimed and none is measurable here.
- This build is private until the maintainer decides to publish it. Nothing here is published,
  pushed, or made public without the owner's explicit go.
