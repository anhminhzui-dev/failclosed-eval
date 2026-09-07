# failclosed-eval

[![CI](https://github.com/anhminhzui-dev/failclosed-eval/actions/workflows/ci.yml/badge.svg)](https://github.com/anhminhzui-dev/failclosed-eval/actions/workflows/ci.yml)
[![Licence](https://img.shields.io/badge/licence-evaluation--only-blue)](LICENSE)

A fail-closed admission layer that refuses a non-deterministic grader's input rather than trust it.

**A dry run of this design over 2,232 criterion units returned 1,866 valid and 366 invalid. The
verdict was HOLD. The paid run was never started.** This package is the admission layer that
produced that refusal, extracted onto synthetic data — I built the thing that told me not to spend
the money, and then I obeyed it.

A fail-closed admission layer for measuring a non-deterministic grader. It assumes the measurement
will be wrong and makes that expensive: an item that needs a figure cannot be sent without one, a
prompt that carries a value-shaped label is refused, two independent estimates that disagree abstain
instead of committing, and every admitted unit carries a hash of the exact bytes that produced it.
Nothing averages past a defect. The run returns GO only when every gate passes and every criterion
has a real denominator; everything else, including a crash, returns HOLD.

The system those 2,232 units belong to is not in this repository and nothing here can check that
number — it is stated as the origin of the design, with no accuracy claim attached to it or to
anything else. **No accuracy is claimed and none is measurable here.** Every row in `fixtures/` is
invented.

---

## Why this exists

This is not built against one named job posting the way the six single-day prototypes in this
author's portfolio are. It answers a requirement that recurs across evaluation-engineer and
AI-safety postings in general: a harness that assumes a non-deterministic grader will be wrong,
refuses on missing evidence rather than guessing past it, and proves that it refused with a hash
rather than a sentence. That is the shape this repository demonstrates, extracted from a private
system so the design can be read and run on its own.

---

## Try it in 60 seconds

```bash
git clone https://github.com/anhminhzui-dev/failclosed-eval.git
cd failclosed-eval
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m failclosed_eval.cli run --units fixtures/clean_units.jsonl --policy fixtures/policy.json
PYTHONPATH=src python -m failclosed_eval.cli run --units fixtures/bad_missing_image.jsonl --policy fixtures/policy.json
```

Real output, pasted from a run on 2026-09-07, this repository, no edits:

```console
239 passed in 1.82s

DENOMINATORS: per criterion, one row each
  CORRECTNESS  n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  COMPLETENESS n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  CLARITY      n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  EVIDENCE     n=2 weight=2 refused=0 abstained=0 reference_excluded=0
REFUSALS: none
VERDICT: GO

DENOMINATORS: per criterion, one row each
  CORRECTNESS  n=1 weight=1 refused=1 abstained=0 reference_excluded=0
  COMPLETENESS n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  CLARITY      n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  EVIDENCE     n=2 weight=2 refused=0 abstained=0 reference_excluded=0
REFUSALS: INPUT_IMAGE_REQUIRED=1
VERDICT: HOLD (refused units)
```

This repository is private; a reviewer is given clone access on request. The full refusal-code
table is directly below, and the complete walkthrough, including a third fixture that halts the
whole run instead of refusing one unit, is under "Run it" further down this page.

---

## Boundaries

What this package does not prove, stated plainly:

- No accuracy figure. Every fixture under `fixtures/` is invented; nothing here is graded against a
  real answer.
- No benchmark. The 2,000-unit generated run further down this page is a scale demonstration, not a
  comparison against any other system.
- The abstain thresholds and the anomaly-detection constants are design constants copied from the
  shape of a private system, not values validated against real data.
- The label-leak scanner only catches a digit-shaped value glued to a label word; a value spelled in
  words (`score: seven`) is out of scope by design, not by oversight.
- MLflow tracking is optional and off by default; when it is on, it logs validity counts only, never
  an estimate or a reference value.

---

## What it refuses

Every unit that enters a run passes through two tiers of gate. Both tiers are fail-closed: when a
gate cannot decide, the answer is refuse or halt, never pass.

**Tier 1 — unit refusal.** One unit is rejected, counted, and named in the run's trace. The run keeps
going so the operator sees the whole picture, but a single tier-1 refusal is enough to force the
final verdict to `HOLD`.

| Code | What triggers it |
|---|---|
| `INPUT_IMAGE_REQUIRED` | the item type needs a figure and no image bytes resolved |
| `MISSING_INSTRUCTION` | a text item has no instruction text |
| `UNRESOLVED_IMAGE` | an image path was given but the file is not there |
| `INVALID_IMAGE_PAYLOAD` | the inline image data is malformed |
| `LABEL_LEAK_IN_PROMPT` | a value-carrying label was found in the prompt text |
| `IMAGE_SLOT_MISSING` | the image slot failed its own post-build self-check (unreachable by design) |

**Tier 2 — run halt.** The whole run stops immediately, a `halt.json` file is written, and the
verdict is `HOLD`.

| Code | What triggers it |
|---|---|
| `NOT_SYNTHETIC` | a row is missing the synthetic marker (the public-clean guard — see below) |
| `MALFORMED_UNITS_FILE` / `EMPTY_UNITS_FILE` | the units file cannot be read or has no rows |
| `MISSING_POLICY_FIELD` / `INVALID_POLICY` | the policy file is incomplete or unusable |
| `MISSING_ITEM_ID` | a row has no item identifier |
| `UNKNOWN_CRITERION` / `UNKNOWN_ITEM_TYPE` | a row names a criterion or item type outside the rubric |
| `DUPLICATE_UNIT` | the same (item, criterion) pair appears twice |
| `MISSING_COMPONENT_EVIDENCE` | the evidence behind an estimate is absent, empty, or unusable |
| `INVALID_WEIGHT` | a unit's weight is negative or not a real number |
| `INVALID_ESTIMATE_VALUE` | a committed value or reference is not a real number |
| `ANOMALOUS_ESTIMATE` | a value sits at the floor while its supporting evidence is high — a broken measurement, not a low one |
| `ANOMALOUS_DISTRIBUTION` | one value holds an outsized share of a criterion's rows |
| `MISSING_DENOMINATOR` | a criterion ends the run with nothing admitted, or zero effective weight |

Abstention and a missing reference value are **not** defects. They are counted in their own columns
and named in the run's denominator line, exactly like every other outcome — a unit that abstains is
honest, not broken.

The run's own public-clean guard belongs here too: every synthetic row in this repository must carry
`"synthetic": true`. A row without it halts the run (`NOT_SYNTHETIC`) unless the operator explicitly
passes `--allow-nonsynthetic`. This exists so the shipped package cannot silently ingest real data.

**The default verdict is `HOLD`.** `GO` is earned, not assumed: it requires no halt, zero tier-1
refusals, and every criterion ending with at least one admitted unit and a positive weight. An
unhandled exception at the command-line boundary is also reported as `HOLD` — the refusal is the
default, not the exception.

---

## Why the label regex has no word boundary

A first attempt at a leak scanner used a leading word-boundary anchor on each label word. That is
the wrong choice, for a specific reason: an underscore is a "word" character to a regex engine, so a
word boundary fails exactly where a leak likes to hide — inside a field name, glued directly onto a
digit with nothing separating them. The example below shows the shape.

The second thing that trips a naive scanner is punctuation. The JSON form of a leaked label has more
separator characters between the word and the value than the plain form does — a quote, then a
colon, then a space, versus just a colon and a space. A single *optional* separator character catches
the plain form and misses the quoted JSON form; the fix is a *repeated* separator class, not a single
optional one, as the second and third examples below show.

So the pattern this package uses drops the leading boundary and repeats its separator classes. A few
worked examples (each line below carries the detector's own exemption anchor,
LABEL-LEAK-DETECTOR-SOURCE, so this documentation is never mistaken for the thing it documents):

- `"lev" + "el: 3"` → a hit. LABEL-LEAK-DETECTOR-SOURCE
- `'{"lev' + 'el": 3}'` → a hit, because the separator class is repeated. LABEL-LEAK-DETECTOR-SOURCE
- `"item_lev" + "el5"` → a hit, because there is no leading word boundary. LABEL-LEAK-DETECTOR-SOURCE
- `"the level of detail is good"` → **not** a hit — no digit follows. LABEL-LEAK-DETECTOR-SOURCE
- `"You must never output a level or a score."` → **not** a hit, same reason. LABEL-LEAK-DETECTOR-SOURCE

That last pair of examples is the point of the whole design: **only value-carrying patterns count.**
A bare label word is never a hit on its own. A prompt that instructs a model never to output a value
has to *name* the forbidden words in order to forbid them — so a scanner that flags the bare word
punishes the prompt that complies hardest, and lets the actual leak (the word glued to a digit) pass
if it is spelled carelessly.

### What that argument cost, measured

The first version of this pattern dropped the leading boundary and stopped there, and it was wrong
in a way the README argued its way past. With no assertion at all in front of the label word, every
ordinary English word that *ends* in one of them — a benchmark year, a landmark number, an upgrade
release — fired, and a legitimate unit was thrown out of the denominator and the run was held.

The cure is one lookbehind: the label word must be preceded by a **non-letter or the start of the
string**, `(?<![a-z])`. An underscore is not a letter, so the identifier case above still fires;
`benchmark` and `upgrade` no longer do.

The measurement is `fixtures/fp_corpus_instructions.txt`: 250 invented instruction lines, every one
of them legitimately carrying a label word together with a digit.

| Pattern | Lines that fired | Rate |
|---|---|---|
| first version, no assertion in front | 87 of 250 | **34.80%** |
| shipped version, non-letter lookbehind | 4 of 250 | **1.60%** |

The four that remain are one shape and one shape only: a standalone label word with a digit welded
straight to it. That is structurally identical to a real leak, so the detector cannot separate them
and does not pretend to; the four lines are labelled as such at the end of the corpus, and a test
asserts that nothing outside that block fires, so a new false-positive class cannot hide inside a
rate that still looks small.

**Out of scope, stated rather than left as a hole: a value spelled in words is not caught.** The
pattern is digit-shaped, so `score: seven` and a value written as a word return zero. That is a
known limit, it is pinned by a test as documented behaviour, and it is why this scanner is one gate
among several rather than the only thing standing between a prompt and a leak.

Both directions are proven in the test suite rather than asserted here: the value-carrying cases
must fire, the bare-word cases must not, the corpus rate must stay under two percent, and the two
copies of the pattern — the one in the admission path and the one in the repository scan — must be
byte-identical.

The same scanner runs twice: once inside the admission path (`validators.build_payload`, over every
prompt before it is sent) and once as a standalone repository scan (`scripts/forbidden_scan.py`, over
every shipped file). Both carry the same exemption rule: a line containing the anchor token above is
skipped. Without that exemption, a scanner that explains itself would refuse itself — the failure
this project is built to avoid.

---

## Abstain instead of committing

When a unit carries more than one independent estimate, the package does not average them. It looks
at how much they disagree:

- **Zero estimates** → abstain (`"no estimate"`) — there is nothing to abstain from disagreeing on.
- **One estimate** → commit it. One value cannot disagree with anything.
- **Two or more estimates** → compute their spread (max minus min) and their population standard
  deviation. If either crosses a threshold, the unit **abstains** instead of committing a value. Below
  both thresholds, it commits the *median*, rounded to the rubric's step size.

The two thresholds that decide "disagree" are **design constants copied from the shape of the
original system, not validated operating points.** No experiment in this repository set them, and
none is claimed to have. Anyone adopting this package should treat them as a starting point to
calibrate against their own data, not as a tuned default.

---

## Provenance

Every admitted unit carries `input_sha256`: a SHA-256 hash of the exact payload that was built for
it, computed over a canonical, key-order-independent JSON form, so the same content always hashes
the same way regardless of field order. A figure item also carries `image_sha256`, the hash of the
image bytes actually resolved into that payload; a text item carries `null` there.

What this proves: a later reader can confirm which exact bytes produced a given unit, without ever
being handed those bytes back. What it deliberately does **not** carry: no estimate, no reference
value, no component evidence, and no weight ever appears in the trace file. The point of a provenance
hash is to prove *what went in*, not to republish *what came out* — those two things are kept in
different files on purpose, and the trace file is the one that ships with a hash but never a value.

---

## The reference value is collected and then stops

Every unit carries a `reference`. It is read from the row, validated as a finite number, stored on
the admitted unit — and used by nothing. Grep `.reference` across `src/` and the only hit is the
field declaration.

**That is a boundary, not an unfinished feature.** Comparing an estimate against a reference is how
an accuracy figure is made, and an accuracy figure computed over invented fixtures would be a number
about invented data wearing the clothes of a result. The field is admitted and validated because a
unit whose reference is malformed is a malformed unit; it stops there on purpose. A test walks every
file the package writes — `summary.json`, `trace.jsonl`, `halt.json`, on the clean path and on the
halted one — and fails if a number appears under any key that is not a declared count, so an
accuracy figure cannot arrive here quietly.

---

## Run it

The package lives under `src/` and these examples never install it — every command below sets
`PYTHONPATH=src` for that reason. Set it once per shell, or let each command set it inline (every
block below does the inline form, so a single copy-pasted line always works on its own).

Bash / zsh / macOS / Linux:

```bash
export PYTHONPATH=src
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
```

Windows `cmd.exe`:

```cmd
set PYTHONPATH=src
```

```bash
# A clean synthetic run: every gate passes, every criterion has a denominator.
PYTHONPATH=src python -m failclosed_eval.cli run \
    --units fixtures/clean_units.jsonl \
    --policy fixtures/policy.json
# -> VERDICT: GO, exit code 0

# The same command against a fixture with one seeded defect (a missing required image).
PYTHONPATH=src python -m failclosed_eval.cli run \
    --units fixtures/bad_missing_image.jsonl \
    --policy fixtures/policy.json
# -> VERDICT: HOLD (refused units), exit code 2
```

Add `--out runs/some-name` to either command to also write `summary.json`, `trace.jsonl`, and (on a
halt) `halt.json` to that directory. Exit codes throughout the CLI: `0` for a proven `GO` (or a clean
`scan` / `version`), `2` for `HOLD` or a leak hit from `scan`, `1` for bad usage or an unexpected
error — even a crash reports through the refusal path, never silently.

### What it actually looks like

A clean run and then a refusal, back to back, pasted from a terminal:

```console
$ PYTHONPATH=src python -m failclosed_eval.cli run --units fixtures/clean_units.jsonl --policy fixtures/policy.json
DENOMINATORS: per criterion, one row each
  CORRECTNESS  n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  COMPLETENESS n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  CLARITY      n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  EVIDENCE     n=2 weight=2 refused=0 abstained=0 reference_excluded=0
REFUSALS: none
VERDICT: GO
$ echo $?
0

$ PYTHONPATH=src python -m failclosed_eval.cli run --units fixtures/bad_missing_image.jsonl --policy fixtures/policy.json
DENOMINATORS: per criterion, one row each
  CORRECTNESS  n=1 weight=1 refused=1 abstained=0 reference_excluded=0
  COMPLETENESS n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  CLARITY      n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  EVIDENCE     n=2 weight=2 refused=0 abstained=0 reference_excluded=0
REFUSALS: INPUT_IMAGE_REQUIRED=1
VERDICT: HOLD (refused units)
$ echo $?
2

$ PYTHONPATH=src python -m failclosed_eval.cli run --units fixtures/bad_duplicate.jsonl --policy fixtures/policy.json
DENOMINATORS: PARTIAL - the run halted, so these counts cover only the rows processed before the halt
  CORRECTNESS  n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  COMPLETENESS n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  CLARITY      n=2 weight=2 refused=0 abstained=0 reference_excluded=0
  EVIDENCE     n=2 weight=2 refused=0 abstained=0 reference_excluded=0
REFUSALS: none
HALT: DUPLICATE_UNIT unit_id=syn-001::CORRECTNESS
VERDICT: HOLD (DUPLICATE_UNIT)
$ echo $?
2
```

Two things in that third block are deliberate. The counts are marked **PARTIAL**, because a halt
stops the loop and counts printed above a halt are true only as far as the run got. And the halt
names the unit that caused it, so the operator is told where the run stopped and not merely that it
did.

### At scale

The eight shipped fixtures demonstrate every gate; they do not demonstrate size. The generator
closes that gap, and its output is regenerable rather than committed:

```bash
PYTHONPATH=src python scripts/make_fixtures.py --count 2000 --out fixtures/generated/units_2000.jsonl --verify
PYTHONPATH=src python -m failclosed_eval.cli run     --units fixtures/generated/units_2000.jsonl     --policy fixtures/policy.json --out runs/scale_2000
```

The generator is seeded and stdlib-only: the same `--seed` reproduces the same bytes, and `--verify`
generates twice and compares before writing anything. `fixtures/generated/` is gitignored.

Recorded run, 2,000 units, seed 20260906, 5% of rows seeded with a tier-1 defect, 3% built to
abstain, 2% with no reference value:

| | |
|---|---|
| units selected | 2,000 |
| admitted | 1,800 |
| refused | 100 — `INPUT_IMAGE_REQUIRED` 34, `LABEL_LEAK_IN_PROMPT` 33, `MISSING_INSTRUCTION` 33 |
| abstained | 60 |
| excluded, no reference | 40 |
| verdict | `HOLD (refused units)`, exit 2 |
| trace rows written | 2,000 — one per selected unit, admitted or not |
| wall clock | 0.17 s, median of three runs of the whole command |

The four columns add up to the 2,000 selected, which is the property the denominator line exists to
make checkable: every unit lands in exactly one of them and nothing is quietly dropped.

Run the repository's own self-scan the same way CI does (this script has no dependency on the
package itself, but PYTHONPATH=src is harmless to include and keeps every command on this page
in the same shape):

```bash
PYTHONPATH=src python scripts/forbidden_scan.py --root .
```

---

## Optional MLflow

MLflow is an optional extra (`pip install failclosed-eval[tracking]`), imported inside a `try`/
`except` and never required. Pass `--mlflow` to the CLI to enable it; without the flag, and without
the package installed, `failclosed-eval` runs exactly the same.

When it is enabled, only **validity counts** reach the tracker: how many units were selected,
admitted, refused, abstained, or missing a reference; which criteria ended with zero denominator;
the refusal codes and their counts; the verdict and halt code as tags; the input hashes and package
version as params. **No estimate, no reference value, no component evidence, and no error figure is
ever logged.** That is not a policy note — the object the tracker is handed structurally does not
contain those fields, and a test in this repository logs into a fake tracker and inspects exactly
what it received to prove it.

---

## What this is not

This package makes no accuracy claim and contains no benchmark, no trained model, no network call,
and no real response data of any kind. Every row in `fixtures/` is invented for this repository and
is marked as synthetic; the run refuses to proceed on a row that is not. What is being demonstrated
is a **design**: a way of admitting untrusted, non-deterministic measurements that refuses first and
asks questions never. The design is the artifact, not a result.

---

## The self-scan refused this repository until its owner signed it

`python scripts/forbidden_scan.py --root .` exited 2 on the pre-publication tree, with exactly two
findings: `LICENSE` and `pyproject.toml` each carried an unfilled placeholder where the copyright
holder's name belongs. (The placeholder token is not written out here — this file is scanned too,
and a document that quotes the forbidden string becomes a finding of its own.) **That refusal was
deliberate** — the package's own thesis applied to itself, since a licence and an authorship field
with no holder named are unfilled fields and this scanner's whole job is to refuse unfilled and
forbidden text. Filling in a legal name is the one step a tool must not take on the owner's behalf.
The owner filled both files at publication; the published tree scans to `SCAN: clean` and exit 0,
and the refusal path stays proven in the tests on throwaway trees.

The scan has two halves and both are live. Private shapes — a drive-letter root, a user-home
directory, a personal mailbox at a consumer mail provider — are matched as regexes that name no
machine, no user, no directory and no person. That last rule exists because the hashed half cannot
reach it: the owner's private address and the owner's public code-host handle share a local part, so
denying the word would refuse the public no-reply contact address this package is published with. Private *names* are matched
as sha256 hashes, generated locally with `--hash-tokens` from a token file kept outside this
repository and never committed, so the guard never publishes the words it is guarding. Only the
hashes ship, and a hit prints a hash prefix rather than the word that produced it. Regenerate with
`python scripts/forbidden_scan.py --hash-tokens <local token file>` and paste the block it prints;
if that set were ever empty the scan says so out loud rather than reporting a clean tree from a check
that never ran.

---

## Licence

**Source-available, not open source.** This repository exists to show the work, not to give it away.

Reading it, cloning it, and running it in order to evaluate the author's work is permitted.
Redistribution, modification for distribution, derivative works, and commercial use are not. See
[`LICENSE`](LICENSE) for the operative terms; the copyright holder is named on its first line, and
the repository's own scan would refuse the tree if that line were ever left unfilled.

A standard licence was checked first and rejected against its own text: PolyForm Strict 1.0.0 grants
its copyright licence "for any permitted purpose", and it defines any noncommercial purpose as
permitted — which is far broader than the evaluation-only grant intended here. So this repository
carries a short plain-English Evaluation-Only Licence instead.
