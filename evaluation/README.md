# AutoTest — GenAI Evaluation Layer

An isolated experimentation layer around the AutoTest pipeline. It measures
the two GenAI tasks with a reproducible, fair-comparison methodology:

```text
SCOPE  →  what is measured (two GenAI tasks + RAG retrieval)
SELECT →  which variables can change (prompt, RAG, model) and which never do
         (dataset, temperature, max_tokens, execution environment)
ADAPT & ALIGN → one harness where every variant runs under identical conditions
EVALUATE      → raw + aggregated results, comparison tables
OPTIMIZE      → scaffolded, not started (see optimization/README.md)
```

**The production application is never modified.** This layer imports
production components read-only and runs everything in isolated workspaces
guarded to `evaluation/`.

---

## The two GenAI tasks

| Task | Input | Component | Output |
|------|-------|-----------|--------|
| Test Generation | Python source + AST/RAG context | Test Writer | pytest tests |
| Automated Debugging | failed tests + traceback + source | Debugger | corrected tests |

Production configuration (baseline, fixed, no fallbacks, no `auto`):
- Test Writer: `cohere/north-mini-code:free`
- Debugger: `nvidia/nemotron-3-super-120b-a12b:free`

---

## Dataset

`datasets/corpus.py` defines 15 deterministic samples (unique IDs + metadata):
simple (2), branch (2), edge (2), exception (1), class (2), dependency (1),
difficult (2), and 3 controlled **debug targets** (wrong expected value,
wrong exception type, wrong patch target) that ship a known-buggy test.

`python -m evaluation.build_dataset` materializes `datasets/generated/v1/`
with a SHA-256 manifest. Rebuilds are byte-identical — the recorded
`dataset_hash` proves every experiment used the same data.

---

## Metrics

### Test Writer (primary)
| Metric | Implementation |
|--------|----------------|
| Execution Success Rate | suite collects and runs (production `run_tests_locally`) |
| Pass@1 | all generated tests pass on the first execution |
| Line Coverage | coverage.py JSON (`--cov-branch`) |
| Branch Coverage | coverage.py JSON (`--cov-branch`) |
| Mutation Score | built-in bounded AST mutation engine (≤8 mutants/sample) |
| Invalid-API / hallucination rate | static analysis: referenced names vs available API |
| Latency | wall-clock per sample |
| Token usage | prompt/completion tokens from the LLM response |

### Test Writer (secondary — text similarity ONLY)
BLEU-4, ROUGE-L, simplified CodeBLEU (n-gram + AST-node match) against a
reference test. These are **never** correctness measures — correctness is
execution/coverage/mutation. Perplexity: **not implemented** (OpenRouter
free endpoints don't return logprobs — future work). GLUE: not applicable
to code generation.

### Debugger
Repair success rate · test recovery rate · first-attempt repair rate ·
regression rate · iterations · latency · tokens — driven through the
production `DebuggerLLM` + `apply_fix_safely` in isolated workspaces.

### RAG (retrieval, evaluated separately)
Recall@K · Precision@K · MRR · nDCG against the labeled pattern corpus in an
isolated, deterministically seeded ChromaDB, plus the downstream A/B
(P3 RAG ON vs OFF) to verify whether retrieval actually improves test quality.

---

## Experiments (fair comparison: ONE variable at a time)

| Experiment | Variable | Everything else |
|------------|----------|-----------------|
| `baseline` | none (production config) | fixed |
| `prompts` | P0 (production) / P1 structured / P2 +few-shot / P3 +few-shot | model, RAG, dataset fixed |
| `rag` | P3 RAG OFF vs P3 RAG ON (seeded isolated store) | model, prompt, dataset fixed |
| `retrieval` | retrieval quality only (Recall@K/MRR/nDCG) | — |
| `models` | candidate Test Writer/Debugger models | P0 prompt, dataset fixed |
| `debugger` | candidate debugger models | dataset, caps fixed |

Results are **append-only**: `results/<name>_<timestamp>_<uid>/` with
`metadata.json` (model, prompt version, RAG status, dataset version+hash,
temperature, max_tokens, timestamp, environment), `samples/*.json` (raw),
`aggregated.json`. No winner is selected automatically.

---

## Commands

```bash
# Dataset
python -m evaluation.build_dataset

# Smoke test (2 writer samples + 1 debug sample, real LLM, no mutation)
python -m evaluation.smoke

# Experiments
python -m evaluation.run_experiment --experiment baseline
python -m evaluation.run_experiment --experiment prompts --full
python -m evaluation.run_experiment --experiment rag --full
python -m evaluation.run_experiment --experiment retrieval
python -m evaluation.run_experiment --experiment models --writer-model <slug> [--full]
python -m evaluation.run_experiment --experiment debugger --full

# Comparison report across stored experiments
python -m evaluation.report --latest
python -m evaluation.report --experiments baseline_<id> prompt_p1_<id>
```

Free-tier friendly: `--samples N` limits scope; mutation is off unless
`--full` (or `--mutation`); a 2-second pacing sits between LLM calls.

---

## Isolation guarantees

1. **No production modifications** — the layer imports production modules
   and never writes outside `evaluation/` (enforced by
   `isolation.ensure_under_evaluation`).
2. **No production RAG mutation** — experiments use either read-only access
   or isolated seeded stores (`RAGMemory(persist_directory=<eval dir>)`).
3. **Model overrides are in-process only** (`llm.service._services` patched
   and restored) — production configuration files are untouched.
4. **Production logs untouched** — prompt/raw-response logging is redirected
   into the experiment workspace during runs.
5. **No secrets stored** — every result JSON passes a scrubber; a leak scan
   runs in the smoke test.

---

## What is ready now vs future work

**Ready:** dataset (deterministic, hashed) · baseline · prompt variants
(P0–P3) · RAG A/B + retrieval metrics · model-comparison framework ·
debugger repair metrics · comparison reports · append-only storage ·
secret scrubbing.

**Future work (scaffolded in `optimization/README.md`):** prompt
optimization iterations, knowledge distillation, local student models,
quantization (FP16/INT8/INT4 — local models only), pruning. Perplexity
metrics when logprobs become available.
