# Public-data offline run receipt

This receipt records one offline run of this repository's admission layer over a real, public,
freely downloadable essay dataset. No model, grader, or paid API of any kind was called at any
point; every number below comes from the repository's own shipped code (`validators.build_payload`,
`validators.scan_paths_for_leaks`, and the `failclosed-eval` CLI's `scan` subcommand) running
unmodified against the data cited here. The portable reproduction is now included at
`scripts/run_public_admission.py`; it requires an existing copy of the cited CSV and a new
output directory outside the checkout. The script makes no network call.

## Dataset

- **Name:** ELLIPSE Corpus (English Language Learner Insight, Proficiency and Skills Evaluation)
- **URL:** https://github.com/scrosseye/ELLIPSE-Corpus (training file fetched from
  `https://raw.githubusercontent.com/scrosseye/ELLIPSE-Corpus/main/ELLIPSE_Final_github_train.csv`,
  no login or account required)
- **Licence:** CC BY-NC-SA 4.0 (Attribution-NonCommercial-ShareAlike 4.0 International)
- **Citation:** Crossley, S. A., et al. (2023). "Measuring second language proficiency using the
  English Language Learner Insight, Proficiency and Skills Evaluation (ELLIPSE) Corpus."
  *International Journal of Learner Corpus Research*, 9(2), 248-269.
- **n used:** 500 essays, out of 3,911 rows in the cited training split (the first 500 rows in
  file order, a deterministic slice).
- **CSV SHA256 reproduced:** `782344e99668a3ff508d7410c0eb6e36da70f3b28f81c96e367f1ca04924b06c`.
- The essay data is **not** committed to this repository and never will be; it lives outside the
  repository tree, in a local working directory, and is excluded from every command below except
  as an input path.

## What this run does and does not cover

This run exercises the **Tier-1 admission layer only**: `validators.build_payload` (payload
construction, the mandatory image slot, the two label-leak regexes) and the label-leak scanner
(`scan_paths_for_leaks`, the same function the shipped `scan` subcommand calls). It does **not**
invoke the full `run()` pipeline or the CLI's `run` subcommand (abstain, the anomaly halts, or the
per-criterion denominator check), because that pipeline requires per-unit grading evidence
(`estimates`, `component_evidence`, a `reference`) that only a real grading call produces, and no
grading call of any kind was made here. Manufacturing placeholder numbers for those fields to
force the full pipeline to run would misrepresent what this run actually measured, so they were
left out rather than invented.

## Unit construction

Each of the 500 essays became one unit record following the JSONL contract documented in this
repository's own `README.md` and `src/failclosed_eval/validators.py`: `criterion` cycles through
the four pinned rubric criteria (`CORRECTNESS`, `COMPLETENESS`, `CLARITY`, `EVIDENCE`) in order,
`instruction` is the rubric's own unmodified `CRITERION_QUESTIONS` text for that criterion, and
`response_text` is the essay's `full_text` column, verbatim and unmodified.

The first five rows of each block of twenty receive one defect each: zero-based row index
modulo twenty selects shapes 0 through 4. Across 500 rows this produces 25 examples of each
shape, or 125 deliberately modified units. This uses the construction technique that
this repository's own
`scripts/make_fixtures.py` already uses for its seeded-bad rows, so every reachable Tier-1
refusal code is proven to fire on real essay-shaped structure at least once:

| Seeded shape | Rows | Refusal code it must produce |
|---|---|---|
| `item_type` set to `figure`, no image supplied | 25 | `INPUT_IMAGE_REQUIRED` |
| `instruction` blanked | 25 | `MISSING_INSTRUCTION` |
| a constructed value-carrying label appended to the instruction | 25 | `LABEL_LEAK_IN_PROMPT` |
| `image_path` pointed at a file that does not exist | 25 | `UNRESOLVED_IMAGE` |
| `image_data_uri` given a well-formed header but invalid base64 payload | 25 | `INVALID_IMAGE_PAYLOAD` |

The remaining 375 of 500 rows are unmodified public essay text and rubric-native instructions,
with no constructed defect.

## Commands used

Save the linked training CSV outside the repository, respecting the dataset licence. From
the repository root, pass its actual path and an output directory that does not yet exist:

```bash
python scripts/run_public_admission.py \
  --csv ../ELLIPSE_Final_github_train.csv --output ../public-run-reproduction
PYTHONPATH=src python -m failclosed_eval.cli scan --root ../public-run-reproduction/essays_txt
python -m pytest -q
```

On PowerShell, set `$env:PYTHONPATH='src'` before the scanner command and put the reproduction
command on one line. The script writes only to the requested new output directory, refuses
to overwrite an existing directory, reports the input CSV hash and observed counts, and
returns exit 0 only when the counts below reproduce (otherwise exit 2). Its row ids are
position-based rather than derived from untrusted CSV identifiers. Essay data stays out of Git.
The separate scanner command is expected to exit 2 because the planted probe must fire.

## Counts

**Payload construction (`build_payload`, 500 of 500 units):**

| | Count | Out of |
|---|---|---|
| Valid (payload built, no refusal) | 375 | 500 |
| Invalid (refused) | 125 | 500 |

**Refusal codes (125 of 500 refused units):**

| Code | Count | Out of |
|---|---|---|
| `INPUT_IMAGE_REQUIRED` | 25 | 125 |
| `MISSING_INSTRUCTION` | 25 | 125 |
| `LABEL_LEAK_IN_PROMPT` | 25 | 125 |
| `UNRESOLVED_IMAGE` | 25 | 125 |
| `INVALID_IMAGE_PAYLOAD` | 25 | 125 |

Every seeded shape produced exactly its intended code and no other code, across all 25 of its
own rows and zero of every other shape's rows.

**Label-leak scan, independent pattern tally (1,000 text fields: 500 instructions + 500
response texts, counted with the repository's own compiled regexes, `LABEL_LEAK_RE` and
`VERDICT_LEAK_RE`, before any refusal short-circuits the check):**

| Pattern | Hits | Out of 1,000 fields checked |
|---|---|---|
| `LABEL_LEAK_RE` | 25 | 25 of 1,000 fields |
| `VERDICT_LEAK_RE` | 0 | 0 of 1,000 fields |

All 25 hits trace to the deliberately seeded instructions. All 500 essay-response fields
remain unmodified and carried zero organic hits of either pattern.

**Leak scan via the shipped CLI (`scan` subcommand, 501 files: 500 essay `.txt` dumps plus one
seeded negative-control probe file):**

- Files with a hit: 1 of 501 (`_seeded_negative_probe.txt`)
- Organic hits among the 500 real essay files: 0 of 500
- CLI exit code: `2` (a hit was found, matching the documented "`2` for HOLD or a leak hit from
  `scan`" contract)
- Seeded negative case: **fired as designed** (hit count 1, matching the constructed positive
  it was built to catch). The repository's own existing positive-control test,
  `test_label_leak_detector_can_itself_fail_on_a_constructed_positive`, also still passes; see
  the test-suite run below.

## Test suite

```
$ PYTHONPATH=src python -m pytest -q
239 passed in 2.08s
```

239 of 239 tests pass, unchanged from before this run: this receipt adds no source-code
changes to `src/`, `scripts/`, `fixtures/`, or `tests/`.

## Runtime

These are observations from the original run, not a runtime guarantee. An independent
7 September rerun of the included portable script reproduced 375 valid / 125 refused,
the five 25-row refusal groups and the 501-file scan (one seeded probe hit). Its payload
pass took 0.0444 seconds. Reusing the output directory was refused without changing its
receipt. No dataset download or model call was needed for that rerun.

| Step | Wall clock |
|---|---|
| `scripts/run_admission.py` end to end (CSV load, unit construction, 500 `build_payload` calls, pattern tally, 501-file leak scan, file writes) | 0.87 s |
| `build_payload` calls only, 500 of 500 units | 0.044 s |
| CLI `scan` subcommand, 501 files | 0.52 s |
| Test suite, 239 tests | 2.08 s |

## Boundaries

This is an offline structural-admission run, not a grading run. No model was called, no essay
was graded, no band or score was produced or claimed, and no accuracy figure of any kind is
computed or implied here: there is nothing here to compare against a real score even if one
had been wanted. What is measured is only whether the repository's own shipped admission code,
unmodified, correctly builds a payload from real public text or correctly refuses it, and
whether its label-leak scanner correctly stays silent on 500 real essays while still firing on
one deliberately constructed probe. The reference dataset's own trait scores (`Overall`,
`Cohesion`, `Syntax`, `Vocabulary`, `Phraseology`, `Grammar`, `Conventions`) were not read into
any unit and are not used anywhere in this run, on purpose: this repository's rubric is
domain-neutral and was not built to be compared against another corpus's own scoring scheme, and
doing so would manufacture an accuracy claim this run does not make.
