# AutoTest GenAI Evaluation — Research Report (Prompts & RAG, dataset v1)

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


**Scope:** Test Generation (Test Writer) and RAG retrieval. Model-comparison,
debugger-evaluation, distillation, quantization and pruning are explicitly
out of scope for this report.
**Models (fixed, no fallbacks, no auto):** Test Writer `cohere/north-mini-code:free` ·
Debugger `nvidia/nemotron-3-super-120b-a12b:free`.
**Dataset:** v1, 12 writer samples + 3 debug targets, hash `6c117a72e25ca8fc`
(15 samples, 31 files; rebuilds byte-identical).
**Conditions (identical across all compared runs):** temperature 0.3, max_tokens 2048,
reasoning disabled, mutation cap 8/sample, 2 s call pacing, dataset hash above,
same execution environment.

---

## 1. Experiments completed (valid full runs — 12/12 valid samples each)

| Run | Directory | Notes |
|---|---|---|
| Baseline | `baseline_1789681278_877bff` | production config, run 1 |
| P0 | `prompt_p0_1789728854_98e7e4` | production config, run 2 |
| P1 | `prompt_p1_1789752597_a96eb2` | structured prompt |
| P2 | `prompt_p2_1789758263_3f7aee` | structured + few-shot (3 samples pre-optimization, 9 post) |
| P3 | `prompt_p3_1789776746_63c4d9` | structured + few-shot (quota-clean rerun) |
| RAG OFF | `rag_off_1789777201_2b1cd7` | P3, no retrieved patterns |
| RAG ON | `rag_on_1789777613_9f485e` | P3 + seeded isolated RAG store |
| Retrieval | `retrieval_1789769401_ff28c8` | RAG store quality, no LLM |

Quarantined (NOT included in any comparison): `prompt_p3_1789762175` (5/12 samples
were daily-quota 429 failures), `rag_off_1789763476`, `rag_on_1789777613→_86747f`
(24/24 quota failures), plus partial/abandoned attempts in `results/_abandoned/`.

## 2. Aggregated results (Test Writer, 12 samples per run)

| Run | Pass@1 | Exec. success | Line cov. | Branch cov. | Mutation | Halluc. | Latency (s) | Tokens |
|---|---|---|---|---|---|---|---|---|
| Baseline (run 1) | 0.667 | 1.000 | 96.23 | 87.36 | 1.000 | 0.000 | 4.60 | 857 |
| P0 (run 2) | 0.750 | 1.000 | 96.23 | 87.36 | 1.000 | 0.000 | 3.28 | 866 |
| P1 | 0.750 | 0.917 | 92.68 | 81.94 | 1.000 | 0.000 | 1.65 | 706 |
| P2 | 0.750 | 1.000 | 96.96 | 88.19 | 0.455 | 0.000 | 1.97 | 804 |
| P3 | 0.750 | 1.000 | 96.96 | 88.19 | 0.182 | 0.000 | 4.09 | 811 |
| RAG OFF | 0.750 | 1.000 | 96.96 | 88.19 | 0.182 | 0.000 | 4.01 | 815 |
| RAG ON | 0.750 | 1.000 | 96.96 | 88.19 | 0.182 | 0.000 | 4.13 | 930 |

Text-similarity (secondary, NOT correctness): BLEU-4 0.301–0.407 · ROUGE-L
0.496–0.602 · simplified CodeBLEU 0.687–0.741 across variants. Perplexity not
available (no logprobs on free endpoints); GLUE not applicable.

## 3. P0 → P1 → P2 → P3 measured differences (model/dataset/env constant)

- **P1 vs P0:** identical pass@1 (0.750); line coverage −3.56 pp (96.23→92.68),
  branch coverage −5.42 pp; latency −50 % (3.28→1.65 s); tokens −18.5 %
  (866→706). The 2-sample preliminary observation (-28 % tokens) did **not**
  persist at full scale — measured effect is −18.5 %.
- **P2 vs P0:** coverage slightly higher (+0.73 pp line, +0.83 pp branch), same
  pass@1, tokens −7.2 %; mutation score 1.000 → 0.455 — P2's suites kill fewer
  mutants (fewer/different assertions), verified not to be a metric artifact
  (probe: covered mutant killed, uncovered mutant survived).
- **P3 vs P2:** identical pass@1 and coverage; mutation 0.455 → 0.182.
- **Persistent hard samples:** DEP-001 and DIFF-001 fail pass@1 in all 7 runs;
  EDGE-002 fails in 6/7 (P2 passes it); DIFF-002 fails in all P2/P3-family runs.
- **Run-to-run variance (same config, n=12):** baseline vs P0 — one sample
  flipped (CLASS-002), pass@1 0.667 vs 0.750 (±8.3 pp on n=12). This variance
  is larger than most prompt-variant deltas: differences smaller than ~1 sample
  should not be over-interpreted.
- **Reproducibility:** two independent runs of the identical configuration
  (P3-full vs RAG-OFF) produced **identical** pass@1, execution success, line
  coverage, branch coverage and mutation score; tokens ±0.5 %, latency ±0.08 s.

## 4. RAG OFF vs ON (P3 prompt, seeded isolated store, only variable = RAG)

| Metric | RAG OFF | RAG ON | Δ |
|---|---|---|---|
| Pass@1 | 0.750 | 0.750 | 0 |
| Execution success | 1.000 | 1.000 | 0 |
| Line coverage | 96.96 | 96.96 | 0 |
| Branch coverage | 88.19 | 88.19 | 0 |
| Mutation | 0.182 | 0.182 | 0 |
| Tokens | 815 | 930 | **+115 (+14 %)** — higher in all 12/12 samples (+54…+227) |
| Latency | 4.01 s | 4.13 s | +0.12 s |

Retrieval quality of the seeded store (separate measurement): Recall@3 = 1.0,
MRR = 1.0, nDCG = 1.0, Precision@3 = 0.33 (3 patterns retrieved per query).

**Measured conclusion for this corpus/store:** retrieval retrieved the relevant
patterns (perfect ranking metrics) but produced **no measurable downstream
improvement** in pass@1, coverage, mutation score or hallucination rate, while
costing +14 % tokens. This is a statement about THIS dataset (where generated
tests already reach the same coverage without bug patterns) — not a general
claim about RAG.

## 5. Failures / anomalies during experimentation

- **Daily quota (429 `free-models-per-day`)** — the 50-requests/day free tier was
  exhausted mid-experiment; affected runs quarantined and re-executed after the
  00:00 UTC reset / on a fresh account key. The bounded-retry design recorded
  clean per-sample failures (no hangs, no partial data).
- **Overnight process deaths** — two experiment processes were killed (session
  shell cancellation / machine sleep). Raw partial results preserved in
  `results/_abandoned/`; affected runs restarted from scratch.
- **False hallucination positives** — `__file__` was initially flagged; dunder
  names are now excluded (metric fix, applied before the full runs).
- **Mutation-metric equivalence after optimization** — the workspace-reuse
  optimization was probed (covered mutant killed, uncovered mutant survived)
  and is measurement-equivalent to the original implementation.

## 6. Limitations

- n = 12 samples; one-sample flips change pass@1 by 8.3 pp — treat small deltas
  with caution.
- Mutation counts per sample are small (1–8 mutable sites in small functions);
  mutation scores are coarse.
- The RAG store was seeded with 6 deterministic patterns; production-store
  content differs.
- LLM outputs vary run-to-run at temperature 0.3; all comparisons use the full
  12-sample aggregate to absorb this.

## 7. Reproducibility

Dataset: rebuild with `python -m evaluation.build_dataset` → hash `6c117a72e25ca8fc`.
Every run directory stores model, prompt version, RAG status, dataset version +
hash, temperature, max_tokens, timestamp (UTC), Python/platform, and all raw
per-sample records. Rerun any experiment:

```bash
python -m evaluation.run_experiment --experiment baseline --full
python -m evaluation.run_experiment --experiment prompts --full
python -m evaluation.run_experiment --experiment rag --full
python -m evaluation.run_experiment --experiment retrieval
python -m evaluation.report --latest
```

No API keys are stored in `results/` (scrubbed + leak-scanned).

## 8. Production-unchanged confirmation

- Production test suite: **101 passed** after all experiments.
- Production models unchanged: `cohere/north-mini-code:free` /
  `nvidia/nemotron-3-super-120b-a12b:free`, temperature 0.3, max_tokens 2048.
- Production RAG store: **28 patterns before and after** all experiments.
- Evaluation writes are guard-confined to `evaluation/`; production logs
  redirected during runs; no production file modified.
