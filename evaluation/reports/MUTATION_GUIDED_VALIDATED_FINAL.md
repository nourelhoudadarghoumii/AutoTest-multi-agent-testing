# Mutation-Guided Test Generation v2 (Validated) — Final (OPTIMIZE stage)

**Status:** complete. Evaluation-layer experiment only; production AutoTest
untouched. MG-v1 results are preserved unmodified.

## The validity incident (must read first)

During MG-v2 verification, an audit revealed the mutation engine used by
**every earlier experiment** never actually applied mutants to the executed
suites:

- The pre-optimization implementation counted pytest **file-not-found and
  timeout exits as kills** — a passing suite scored 1.0 because each mutant
  "run" hung/failed on infrastructure and the timeout was counted as a kill.
  This also explains the ~5 min/sample wall times observed then.
- The workspace-reuse optimization fixed the hang but imported the
  **original module instead of the mutant** (score 0.0 lower bounds).

**Consequence:** all `mutation_score` values recorded before
`mutation_guided_validated` are artifacts. Pass@1, execution success,
coverage, hallucination rate, latency, tokens, and debugger metrics used
independent measurement paths and remain valid. Historical raw results are
preserved unmodified (append-only); corrected mutation measurement applies
from MG-v2 onward.

**Corrected-engine verification battery** (all passed):
1. Hand-written strong suite kills the real mutants it covers (4/8: `or→and`
   via a negative-score raise test, `<→<=` via a score-0 test, `>=→>` via a
   grade-A boundary test, `0→1` via a score-0 test); the uncovered/equivalent
   survivors survive (quote swaps are behaviorally identical).
2. Assert-True weak suite kills 0/8.
3. Decisive execution proof: pytest output against the `or→and` mutant shows
   `DID NOT RAISE` failures — the mutated copy is what executed.
4. Timeouts are NOT counted as kills (return False).
5. File-not-found is NOT counted as a kill (return False).
6. Deterministic: identical runs → identical results.

## Hypothesis (MG-v2)

Per-test validation against the original, unmutated code (MG-v2) preserves
the mutation-score improvement of mutation-guided generation (MG-v1) while
preventing incorrect generated tests from being merged — recovering Pass@1.

## Method

Identical to MG-v1 (`cohere/north-mini-code:free`, temperature 0.3,
max_tokens 2048, reasoning disabled, RAG OFF, P0 production prompt, dataset
v1 hash `6c117a72e25ca8fc`, 12 writer samples, mutation cap 8, existing
bounded engine) with ONE new variable: after AST validation, each generated
additional test is executed against the **original unmutated code** and is
merged only if the whole suite passes (new test passes, no regression).
Merging is incremental — each accepted test is re-validated in the
accumulated suite. Rejected tests are recorded with reasons and the baseline
suite is kept for that portion.

## Results (12 samples)

**Aggregate:**

| Metric | Value |
|---|---|
| Ceiling-effect samples | 5 (baseline already killed all mutants — no guided step, no extra LLM call) |
| Effective samples | 7 |
| Mutation score Δ (mean, effective) | **+0.262** |
| Mutants killed Δ (mean) | +1.71 per sample |
| Surviving mutants Δ (mean) | −1.86 per sample |
| Line coverage Δ (mean) | +3.17 pp |
| Branch coverage Δ (mean) | +3.57 pp |
| **Pass@1 Δ (mean)** | **0.000 — Pass@1 fully preserved** |
| Additional tests generated | 60 |
| Accepted (validated) | **54** |
| Rejected | **6** (all: `fails_against_original_code`) |
| Tokens Δ (mean) | +179 per sample |
| Latency Δ (mean) | +5.0 s per sample |
| Hallucination rate | 0.000 |
| Rejections in failing-baseline sample (DEP-001) | 6/6 rejected — baseline honestly kept |

**Per-sample:**

| Sample | Ceiling | Base pass@1 | Base mutation | Survivors | Gen | Acc | Rej | Final pass@1 | Final mutation | Final survivors |
|---|---|---|---|---|---|---|---|---|---|---|
| SIMPLE-001 | YES | True | 1.0 | 0 | 0 | 0 | 0 | True | 1.0 | 0 |
| SIMPLE-002 | YES | True | 1.0 | 0 | 0 | 0 | 0 | True | 1.0 | 0 |
| BRANCH-001 | no | True | 0.75 | 2 | 2 | 2 | 0 | True | 0.875 | 0 |
| BRANCH-002 | no | True | 0.75 | 2 | 12 | 12 | 0 | True | 0.875 | 1 |
| EDGE-001 | YES | True | 1.0 | 0 | 0 | 0 | 0 | True | 1.0 | 0 |
| EDGE-002 | YES | False | 1.0 | 0 | 0 | 0 | 0 | False | 1.0 | 0 |
| EXC-001 | no | True | 0.667 | 1 | 5 | 5 | 0 | True | 1.0 | 0 |
| CLASS-001 | no | True | 0.25 | 6 | 13 | 13 | 0 | True | 1.0 | 0 |
| CLASS-002 | no | True | 0.5 | 3 | 6 | 6 | 0 | True | 1.0 | 0 |
| DEP-001 | no | False | 0.833 | 1 | 6 | 0 | 6 | False | 0.833 | 1 |
| DIFF-001 | no | True | 0.875 | 1 | 16 | 16 | 0 | True | 0.875 | 1 |
| DIFF-002 | YES | False | — (0 mutable sites) | 0 | 0 | 0 | 0 | False | — | 0 |

## Answer to the main question

**Can per-test validation recover Pass@1 while preserving most of the
mutation-score improvement? Yes — measured on this dataset.**

- **Pass@1 recovered and preserved:** 7/7 effective samples and 5/5 ceiling
  samples retain their baseline Pass@1 (mean Δ = 0.000). MG-v1's −0.43 pass@1
  regression did not occur: the two tests that failed against the original
  code in MG-v1's BRANCH-001 scenario would have been rejected by the
  validation gate (the gate run demonstrated exactly this rejection).
- **Mutation improvement largely preserved:** +0.262 mean mutation-score
  delta (vs +0.429 raw in MG-v1's unvalidated measurement). 5 of 7 effective
  samples improved mutation score (up to 0.25→1.0 on CLASS-001); two samples
  kept survivors (DIFF-001: the remaining survivor is an equivalent-mutant
  family the model's tests cannot kill; BRANCH-002: 1 of 2 survived).
- **The validation gate worked as specified:** 60 generated additional tests,
  54 accepted, **6 rejected — every rejection because the test failed against
  the original, unmutated code** (DEP-001, where the baseline itself fails).
  No test was merged that broke the suite; the baseline was kept wherever the
  model's additions were invalid.
- **Cost of validation:** +179 tokens and +5.0 s per sample on average
  (generation + per-test validation executions), plus ~1 pytest run per
  additional test.

## Corrected-engine reference measurements (for comparison with MG-v1)

Because MG-v1's stored mutation scores are artifacts, MG-v2's fresh baseline
phase (corrected engine, same config) provides valid reference mutation
scores: mean baseline mutation score across the 7 non-ceiling samples was
0.731 (per-sample: 0.75, 0.75, 0.667, 0.25, 0.5, 0.833, 0.875), rising to
0.929 after validated mutation-guided generation.

## Failures / anomalies

- DEP-001's baseline suite fails pass@1 (a pre-existing property of that
  generated suite); all 6 model-generated repair attempts were correctly
  rejected — the validation layer prevented worsening an already-failing
  suite.
- DIFF-002 generated no mutable sites (recursion/dict logic, no arithmetic or
  boundary constants) — recorded honestly as no-mutants.
- Two infrastructure interruptions occurred during earlier attempts (machine
  sleep/shell cancellation); partial results were quarantined in
  `results/_abandoned/` and the runs re-executed from scratch.

## Limitations

- n = 12; 5 ceiling samples; the +0.262 mean rests on 7 effective samples.
- The bounded engine (8-mutant cap, 6 operator kinds) underestimates the
  mutant space; equivalent mutants (string-quote swaps) are unkillable and
  counted as survivors, deflating scores slightly but consistently across
  arms.
- Free-tier daily quota (50 req/day) bounds how many full experiments can
  run per day.

## Reproducibility

```
python -m evaluation.build_dataset                       # hash 6c117a72e25ca8fc
python -m evaluation.run_experiment --experiment mutation_guided_validated --sample BRANCH-001
python -m evaluation.run_experiment --experiment mutation_guided_validated --full
```
Raw records: `evaluation/results/mutation_guided_validated_1790200572_23ef2b/`.
No API keys stored (scrubbed + leak-scanned). Engine verification battery:
strong suite kills covered mutants, weak suite kills none, mutated module
execution proven via pytest output, timeout/file-not-found not counted as
kills, deterministic.
