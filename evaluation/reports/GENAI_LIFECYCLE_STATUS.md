# GenAI Lifecycle — Status Report

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


**Purpose:** this document is part of the RESEARCH / METHODOLOGY chapter of
the academic internship report. It documents how GenAI technologies were
scoped, selected, adapted/aligned, evaluated, and how the validated
components were integrated into the AutoTest project.

**Important:** the lifecycle itself is a research methodology, NOT a feature
of the deployed AutoTest application. No lifecycle UI exists; AutoTest users
never see it. All lifecycle experiments and artifacts live inside the
isolated `evaluation/` layer. "INTEGRATE / DEPLOY" below refers to the
integration of the validated GenAI components into the internship project.

---

## SCOPE

**Objective.** Define what GenAI is used for in AutoTest and what "good" means.

**Work performed.** Two GenAI tasks were scoped:
1. **Test Generation** — Python source + AST/RAG context → Test Writer → pytest suites.
2. **Automated Debugging** — real pytest failures + traceback + source → Debugger → test-only repairs.

**Constraints & criteria established.** Free OpenRouter models only, one
fixed model per agent, no auto routing, no fallbacks; evaluation criteria:
pass@1, execution success, line/branch coverage, mutation score, invalid-API
(hallucination) rate, latency, token usage; debugger criteria: repair
success, test recovery, first-attempt repair, regression rate, iterations.

**Evidence.** `evaluation/README.md`; production configuration
(`config.py`: `cohere/north-mini-code:free` for the Test Writer,
`nvidia/nemotron-3-super-120b-a12b:free` for the Debugger).

**Remaining work.** None — scope was fixed before experiments.

**Limitations.** Free-tier quota (50 free-model requests/day) constrains
experiment size; accounted for in the experiment design (append-only runs,
quarantine of quota-contaminated runs).

---

## SELECT

**Objective.** Choose the models and retrieval strategy through controlled
comparison, not intuition.

**Work performed.**
- Live OpenRouter catalog scan (447 models, 22 free) filtered for
  Python-code-generation suitability.
- Availability probes before every full run (single call: HTTP 200, correct
  model slug, non-empty content).
- **Test Writer model comparison completed:** reference
  `cohere/north-mini-code:free` vs `deepseek/deepseek-v4-flash-0731:free`
  (valid full runs, 12 samples each, only the model varied);
  `poolside/laguna-s-2.1:free` recorded as **quota-limited** (probe OK,
  full run blocked by the account daily cap — quarantined, not silently
  replaced).
- RAG strategy evaluated separately: retrieval quality (Recall@3, MRR,
  nDCG) plus downstream A/B.

**Evidence.** `evaluation/reports/MODEL_COMPARISON_FINAL.md`;
`evaluation/results/model_deepseek_1789850754_a30599/`;
retrieval metrics in `evaluation/results/retrieval_*/`.

**Key measured results.** deepseek-v4-flash: pass@1 0.917, coverage 95.4/86.1 %,
mutation 0.091, +19 % tokens; reference: pass@1 0.750, coverage 96.2/87.4 %,
mutation 1.000. n = 12 — the pass@1 gap is within run-to-run variance; the
mutation-score gap is the largest measured separation.

**Remaining work.** `poolside/laguna-s-2.1:free` can be completed after the
daily quota reset. More candidates would strengthen the comparison.

**Limitations.** n = 12; single dataset; free-tier models only.

---

## ADAPT & ALIGN

**Objective.** Align model behavior with the task using prompts, retrieval
and output validation — without fine-tuning.

**Work performed.**
- Prompt variants P0 (production) / P1 (structured) / P2 (+few-shot) /
  P3 (+few-shot+RAG) compared on the full dataset — one variable at a time.
- RAG OFF vs RAG ON A/B (P3 prompt, seeded isolated ChromaDB store).
- Retrieval evaluated independently (Recall@3 = 1.0, MRR = 1.0, nDCG = 1.0).
- Output-contract enforcement in production: `<tests>` tags, import
  reconstruction, ast.parse + pytest --collect-only validation,
  reasoning-token disablement (diagnosed via evaluation instrumentation).

**Evidence.** `evaluation/reports/RESEARCH_REPORT_prompts_rag_v1.md`;
`evaluation/results/prompt_p*_*/`, `rag_off_*/`, `rag_on_*/`.

**Key measured results.** P1: −18.5 % tokens, −50 % latency, equal pass@1
(0.750), −3.6 pp line coverage. P2: best coverage (96.96 %) at −7 % tokens
but mutation 0.455. P3: identical coverage/pass to P2, mutation 0.182.
RAG ON: identical downstream quality to RAG OFF, +14 % tokens on this corpus.
Run-to-run variance on n = 12: ±1 sample (±8.3 pp pass@1) — variants whose
deltas are below this band are reported as "no measured difference".

**Remaining work.** None for this stage.

**Limitations.** Small dataset; prompt effects smaller than run-to-run
variance for pass@1.

---

## EVALUATE

**Objective.** Produce reliable, reproducible, contamination-free measurements
for both GenAI tasks.

**Work performed.**
- Deterministic 15-sample dataset (12 writer + 3 debug targets, unique IDs,
  SHA-256 manifest `6c117a72e25ca8fc`).
- Metrics implemented: pass@1, execution success, line/branch coverage
  (coverage.py), mutation score (bounded AST mutation engine, probe-verified),
  hallucination rate, latency, tokens; debugger: repair success, recovery,
  first-attempt repair, regression, iterations; retrieval: Recall@K, MRR, nDCG.
- Append-only results with full metadata; secret scrubbing + leak scans.
- **Debugger research evaluation completed** through the real production
  Executor ↔ Debugger loop with E2B execution
  (`evaluation/reports/DEBUGGER_EVALUATION_FINAL.md`).

**Evidence.** Test Writer: baseline/P0/P1/P2/P3 full runs (12/12 valid
samples each). Debugger: DEBUG-001/002/003 — repair success 3/3, first-
attempt 3/3, regression 0, 6 E2B sandbox passes, all executions real pytest
inside E2B. Contaminated runs (daily-quota 429) quarantined in
`results/_abandoned/` and excluded from every comparison.

**Remaining work.** None — evaluation of both GenAI tasks is complete.

**Limitations.** n = 12 (writer) / n = 3 (debugger); single dataset version;
free-tier quota caps experiment throughput.

---

## OPTIMIZE

**Objective.** Improve measured quality/cost using the evaluation loop.

**Status: COMPLETE — two optimization iterations** (mutation-guided test
generation MG-v1, then validated MG-v2). Optimization began only after the
evaluation results had been analyzed, per the methodology.

**Work performed.** Mutation-guided test generation (evaluation-only, inside
`evaluation/`): the Test Writer receives the REAL surviving mutants of its
own initial suite (id, file/function, line, operator, original/mutated code)
and generates additional targeted tests.
- **MG-v1** (feedback only): mutation score improved but pass@1 regressed
  (tests failing against the original code were merged).
- **MG-v2** (feedback + per-test validation against the original, unmutated
  code): each additional test is merged only if the whole suite passes
  against the original code. Result: mutation improvement preserved
  (+0.262 mean score delta on effective samples; 5/7 samples improved, up to
  0.25→1.0) **and Pass@1 fully preserved** (mean Δ = 0.000). 60 additional
  tests generated, 54 accepted, 6 rejected (all `fails_against_original_
  code`) — no suite was ever worsened.
- During MG-v2 verification, a **mutation-engine validity bug** was
  discovered and fixed: the engine had never actually applied mutants
  (timeouts/file-not-found were counted as kills). All mutation scores
  recorded before MG-v2 are marked as artifacts; other metrics are
  unaffected. Engine now empirically verified (strong/weak suite battery,
  mutated-module execution proof, timeout/missing-file semantics).

**Evidence.** `evaluation/reports/MUTATION_GUIDED_VALIDATED_FINAL.md` (final,
with the validity notice and corrected measurements);
`evaluation/reports/MUTATION_GUIDED_OPTIMIZATION_FINAL.md` (MG-v1, invalid
mutation column marked); raw records in `evaluation/results/mutation_guided_
validated_1790200572_23ef2b/`.

**Key measured results (MG-v2, corrected engine).** 12 samples: 5 ceiling
effects (baseline already perfect — no extra LLM call), 7 effective;
mutation +0.262 mean, coverage +3.2/+3.6 pp, Pass@1 Δ = 0.000, hallucination
0.000, cost +179 tokens/+5.0 s per sample; 60 generated / 54 accepted /
6 rejected tests.

**Remaining work.** None required for the internship scope. Documented
future work: equivalent-mutant filtering (string-quote swaps), expanding the
mutation operator set, prompt optimization along the measured P1 direction
(−18.5 % tokens at equal pass@1).

**Limitations.** n = 12 with 5 ceiling samples (the +0.262 mean rests on 7
samples); bounded 6-operator mutation engine underestimates the mutant
space; free-tier daily quota bounds experiment throughput; knowledge
distillation / local student models / quantization / pruning remain out of
scope (quantization/pruning apply to local models only — not to remote
OpenRouter models).

---

## INTEGRATE / DEPLOY

**Objective.** Integrate the validated GenAI components into AutoTest.

**Work performed.**
- Both agents run in the production LangGraph pipeline
  (Analyser → Test Writer → Executor ↔ Debugger → Reporter) with the fixed
  free models and the shared OpenRouter service (bounded retries, 401/402/403
  never retried, reasoning disabled).
- **E2B execution integrated and proven**: the Executor executes pytest
  inside E2B sandboxes; the Debugger consumes the real sandbox failure
  output and its repairs are re-executed through the same E2B path
  (Executor ↔ Debugger ↔ E2B loop proved end-to-end: failing pass 2/3 →
  repair → passing pass 3/3, two sandboxes, no local fallback when the key
  is configured).
- Frontend surfaces real run data (execution, generated tests, debugger
  timeline, quality, report) backed by the pipeline's actual state.

**Evidence.** `verify_e2b_loop.py` checklist output; `logs/executor/`
records (`mode=e2b_sandbox` for every pass); production suite 102 passed.

**Remaining work.** None for the internship scope.

**Limitations.** Run metadata is in-memory + on-disk JSON (no database);
E2B requires `E2B_API_KEY` (without it, development falls back to local
execution by design).

---

## Summary table

| Stage | Status | Key artifact |
|---|---|---|
| SCOPE | complete | `evaluation/README.md`, production config |
| SELECT | complete (model comparison; 1 candidate quota-limited) | `MODEL_COMPARISON_FINAL.md` |
| ADAPT & ALIGN | complete | `RESEARCH_REPORT_prompts_rag_v1.md` |
| EVALUATE | complete (Test Writer + Debugger) | `DEBUGGER_EVALUATION_FINAL.md`, results/ |
| OPTIMIZE | complete (MG-v1 + validated MG-v2) | `MUTATION_GUIDED_VALIDATED_FINAL.md` |
| INTEGRATE / DEPLOY | complete (E2B loop proven) | `verify_e2b_loop.py`, `logs/executor/` |
