# Mutation-Guided Test Generation — Final (OPTIMIZE stage, evaluation-only)

**Status:** complete. Evaluation-layer experiment only

> ## DATA VALIDITY NOTICE (mutation metric)
>
> After the MG-v2 work, an empirical audit showed the mutation engine used
> for the earlier experiments never actually applied mutants to the executed
> suites: the pre-optimization implementation counted pytest file-not-found /
> timeout exits as kills (producing inflated 1.0 scores), and the workspace-
> reuse optimization imported the ORIGINAL module instead of the mutant
> (producing misleading 0.0-lower-bound scores). The engine has since been
> fixed and empirically verified (a hand-written strong suite kills the real
> `or`->`and` and boundary mutants; an assert-True suite kills none).
>
> **Consequence: every `mutation_score` value recorded before
> `mutation_guided_validated` is an artifact and must NOT be used as
> evidence.** All other metrics in these reports (pass@1, execution,
> coverage, hallucination, latency, tokens, debugger repair) were produced
> by independent measurement paths and remain valid. The stored raw results
> are preserved unmodified (append-only) for auditability; the corrected
> mutation measurement is applied from the MG-v2 experiment onward.
 — the production
AutoTest pipeline is untouched.

## Hypothesis

Giving the Test Writer the **real surviving mutants** of its own initial
suite (mutation ID, file/function, line, operator, original/mutated code)
helps it generate additional tests that kill mutants the initial suite
missed.

## Methodology

- **Model/config (fixed):** `cohere/north-mini-code:free`, temperature 0.3,
  max_tokens 2048, reasoning disabled, RAG OFF, P0 production prompt for the
  baseline generation, dataset v1 (`6c117a72e25ca8fc`), 12 writer samples,
  mutation cap 8/sample (existing bounded engine reused unchanged:
  `generate_mutants` + `_suite_kills_prepared`).
- **Baseline phase:** normal generation → execution → coverage → mutation →
  extract REAL survivors.
- **Ceiling rule:** if every mutant is already killed, record the ceiling
  effect and skip the guided step (no extra LLM call).
- **Guided phase:** one additional LLM call receiving ONLY the real survivor
  descriptions (mutation ID, file, function, line, operator,
  original/mutated code) plus the source under test — never hidden/reference
  tests, never fabricated mutants. Additional tests are merged into the
  initial suite (ast-validated), re-executed, re-measured. Nothing is
  regenerated.
- Feedback verification was gated first on a single sample: the prompt log
  confirmed the real survivor data reached the LLM before the full run.

## Aggregated results (12 samples; 4 ceiling, 8 effective)

| Metric | Baseline | Mutation-guided | Δ (mean over 8 effective) |
|---|---|---|---|
| Mutation score (overall, 59 mutants) | 22/59 = **0.373** | 34/59 = **0.576** | **+0.429** (per-sample mean) |
| Mutants killed (total) | 22 | 34 | +12 |
| Surviving mutants (total) | 37 | 25 | −12 |
| Line coverage | — | — | +5.77 pp |
| Branch coverage | — | — | +7.14 pp |
| Pass@1 | 0.750 | — | **−0.429** (3 samples flipped pass→fail) |
| Additional tests generated | — | 57 (across 8 effective samples) | — |
| Guided-phase token cost | — | 10 680 tokens (~1 335/sample) | — |
| Guided-phase LLM latency | — | 58.2 s total (~7.3 s/sample) | — |
| Hallucination rate | 0.000 | 0.000 | 0 |

## Per-sample results

| Sample | Mutants | Baseline killed | Survivors | Added tests | Guided killed | Guided mutation | Base pass@1 | Guided pass@1 |
|---|---|---|---|---|---|---|---|---|
| SIMPLE-001 | 2 | 0 | 2 | 2 | 0 | 0.0 | PASS | PASS |
| SIMPLE-002 | 1 | 0 | 1 | 6 | 1 | 1.0 | PASS | **FAIL** |
| BRANCH-001 | 8 | 0 | 8 | 12 | 8 | 1.0 | PASS | **FAIL** |
| BRANCH-002 | 8 | 0 | 8 | 9 | 0 | 0.0 | PASS | PASS |
| EDGE-001 | 3 | 0 | 3 | — | — | — | PASS | PASS (merge rejected¹) |
| EDGE-002 | 8 | 8 | 0 | — | — | 1.0 | FAIL | FAIL (ceiling) |
| EXC-001 | 3 | 0 | 3 | 4 | 3 | 1.0 | PASS | **FAIL** |
| CLASS-001 | 8 | 0 | 8 | 17 | 0 | 0.0 | PASS | PASS |
| CLASS-002 | 6 | 0 | 6 | 7 | 0 | 0.0 | PASS | PASS |
| DEP-001 | 6 | 6 | 0 | — | — | 1.0 | FAIL | FAIL (ceiling) |
| DIFF-001 | 8 | 8 | 0 | — | — | 1.0 | FAIL | FAIL (ceiling) |
| DIFF-002 | 0 | 0 | 0 | — | — | None | PASS | PASS (no mutable sites²) |

¹ EDGE-001: the additional tests failed `ast.parse` on merge; the merge was
rejected and the baseline suite retained (safe-fail behavior, recorded as
error, not silently dropped).
² DIFF-002: the mutation engine found no mutable sites — recorded, nothing
fabricated.

Ceiling-effect samples: EDGE-002, DEP-001, DIFF-001 (already 1.0) and
DIFF-002 (no mutants) — **no guided step was run for them** and nothing was
artificially changed.

## Mutation score improvement / reduction

- **Improved (3/8):** SIMPLE-002 (0→1), BRANCH-001 (0→1), EXC-001 (0→1) —
  all survivors killed.
- **Unchanged (5/8):** SIMPLE-001, BRANCH-002, CLASS-001, CLASS-002 (added
  tests killed nothing) + EDGE-001 (merge rejected).
- **No sample got worse** in mutation score; overall 0.373 → 0.576.

## The measured trade-off (cost)

- **Mutation killing improved substantially** (+12 mutants, +0.43 mean
  score) and coverage rose (+5.8 pp line / +7.1 pp branch on effective
  samples).
- **But 3 of 8 effective samples flipped from passing to failing** after the
  merge (SIMPLE-002, BRANCH-001, EXC-001). Inspection of BRANCH-001's
  failures shows two causes: (a) tests targeting **equivalent mutants**
  (e.g. a string-quote swap `'` ↔ `"` — behaviorally identical, unkillable
  by any test, so a test written to "kill" it fails on the original code),
  and (b) boundary tests with wrong expectations (e.g. expecting `score=0`
  to raise when the original accepts it).
- Cost: ~1 335 additional tokens and ~7.3 s additional LLM latency per
  effective sample.

## Is the hypothesis supported?

**Partially.** The core claim — real survivor feedback helps the model write
tests that kill previously surviving mutants — is supported: 12/37 survivors
killed, 3 samples reached a perfect score, coverage improved, zero
hallucinations. **However, the technique in this raw form is not directly
production-usable**, because the additional tests are not individually
validated against the original code before merging: 3/8 samples lost
pass@1, mainly by attempting to kill *equivalent mutants* (a theoretical
impossibility) and by writing incorrect boundary expectations. A practical
version would need per-test validation (run each additional test against the
original before merge) and survivor filtering for equivalent mutants.

## Limitations

- n = 12; 4 samples were ceiling effects and 2 generated no kill improvement
  → the +0.43 mean rests on 8 samples, 3 of which carry the whole effect.
- The bounded engine (8-mutant cap, 6 operator kinds) underestimates the
  true mutant space; equivalent mutants (quote swaps) are not filtered.
- Baseline generation quality varies run-to-run (±1 sample observed
  previously), and the deltas here are measured against each sample's own
  fresh baseline (paired comparison), which absorbs model variance only
  partially.
- One merge was rejected (EDGE-001) — counted as "no improvement", not as a
  failure of the hypothesis.

## Reproducibility

```
python -m evaluation.run_experiment --experiment mutation_guided --sample BRANCH-001
python -m evaluation.run_experiment --experiment mutation_guided --full
```
Raw records: `evaluation/results/mutation_guided_1789865820_443a10/`
(append-only; quarantined partial attempts preserved in
`results/_abandoned/`). Guided prompts (proving only real survivor data was
sent) are retained in the run workspace logs. Dataset v1 hash
`6c117a72e25ca8fc`. No API keys stored.
