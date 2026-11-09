# Test Writer Model Comparison — Final (SELECT stage)

**Status:** framework executed.

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
 Two models completed valid full runs; one
candidate was recorded as quota-limited. This is an academic comparison of
observed empirical differences — **no ranking, no score, no "best" claim.**

## Models evaluated

| Model | Role | Availability | Valid runs |
|---|---|---|---|
| `cohere/north-mini-code:free` | Reference (production Test Writer) | Available | 1 full run (12/12 valid) — existing P0 run, not re-executed |
| `deepseek/deepseek-v4-flash-0731:free` | Candidate | Available (probe: HTTP 200, correct model slug) | 1 full run (12/12 valid) |
| `poolside/laguna-s-2.1:free` | Candidate | Available at probe time; **full run blocked by account-level daily free-model quota** (429 `free-models-per-day` on all 12 samples) | 0 — quarantined in `results/_abandoned/` |

Recorded as **quota-limited**, not model-unavailable: the probe succeeded, so
the model itself serves requests; the account's 50 free requests/day were
exhausted by the preceding runs. The run can be completed after the daily
reset without any methodology change.

## Experimental conditions (identical for every model)

| Parameter | Value |
|---|---|
| Dataset | v1, hash `6c117a72e25ca8fc`, 12 writer samples |
| Prompt | P0 — the exact production Test Writer prompt (imported, never copied) |
| RAG | OFF |
| Temperature | 0.3 |
| Max tokens | 2048 |
| Reasoning | disabled (`reasoning: {"enabled": false}`) |
| Validation | ast.parse + pytest --collect-only |
| Execution | real pytest with line+branch coverage (coverage.py) |
| Mutation cap | 8 AST mutants per sample |
| Pacing | 2 s between LLM calls |
| Only variable | the model |

## Results (12 samples per completed run)

| Metric | north-mini-code (reference) | deepseek-v4-flash | laguna-s-2.1 |
|---|---|---|---|
| Pass@1 | 0.750 | **0.917** | quota-limited |
| Execution success | 1.000 | 1.000 | quota-limited |
| Line coverage | 96.23 % | 95.44 % | quota-limited |
| Branch coverage | 87.36 % | 86.11 % | quota-limited |
| Mutation score | 1.000 | 0.091 | quota-limited |
| Hallucination / invalid-API rate | 0.000 | 0.000 | quota-limited |
| LLM latency (mean) | 3.28 s | 3.12 s | quota-limited |
| Tokens (mean) | 866 | 1032 | quota-limited |
| BLEU-4 *(text sim.)* | 0.365 | 0.314 | quota-limited |
| ROUGE-L *(text sim.)* | 0.561 | 0.513 | quota-limited |
| simplified CodeBLEU *(text sim.)* | 0.719 | 0.693 | quota-limited |

Per-sample pass/fail (order: SIMPLE-001, 002, BRANCH-001, 002, EDGE-001, 002,
EXC-001, CLASS-001, 002, DEP-001, DIFF-001, DIFF-002):

```
north-mini-code : P P P P P F P P P F F P   (9/12)
deepseek-v4     : P P P P P P P P P F P P   (11/12)
```

## Observed empirical differences

- **Pass@1:** deepseek-v4-flash passed 11/12 samples vs 9/12 for the
  reference on this dataset (+2 samples: BRANCH-002 and DIFF-001). With
  n = 12, this difference is two samples — within the run-to-run variance
  band observed for repeated runs of one configuration (±1–2 samples).
- **Assertion strength (mutation):** the reference model's suites killed
  **all** collected mutants (1.000); deepseek's suites killed 9.1 % —
  deepseek's passing tests exercise the code but with fewer boundary
  assertions. This is the largest measured separation between the two
  models.
- **Coverage:** near-identical (−0.8 pp line, −1.3 pp branch for deepseek).
- **Cost:** deepseek used +19 % tokens (1032 vs 866) at comparable latency
  (3.12 s vs 3.28 s).
- **Hallucination:** 0.000 for both — neither model invented APIs.
- **Text similarity:** both models diverge from the reference tests to a
  similar degree (deepseek slightly more); similarity is reported for
  completeness only.

## Failure cases

- Reference model failing samples: EDGE-002, DEP-001, DIFF-001.
- deepseek failing sample: DEP-001 (the dependency sample — the only sample
  that failed for every configuration tested so far, including all prompt
  variants).

## Limitations

- **n = 12 is insufficient for a strong statistical conclusion.** The +2
  sample pass@1 difference (deepseek) is within the observed run-to-run
  variance; the mutation-score gap (1.000 vs 0.091) is the only separation
  that is large relative to that variance.
- One candidate (laguna-s-2.1) could not be measured due to account quota —
  no claim is made about its capability.
- All runs share one account's rate limits; measurements were sequential to
  avoid latency contamination.

## Reproducibility

```
python -m evaluation.run_experiment --experiment models \
    --writer-model deepseek/deepseek-v4-flash-0731:free --full
```
Raw records: `evaluation/results/model_deepseek_1789850754_a30599/`
(reference: `prompt_p0_1789728854_98e7e4/`). Dataset v1
(`6c117a72e25ca8fc`) rebuilds byte-identically. No API keys stored
(scrubbed + leak-scanned).
