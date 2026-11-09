# Debugger Evaluation — Final (Research)

**Status:** research evaluation COMPLETE (distinct from the earlier E2B
framework smoke verification, which proved the infrastructure on one sample
and is NOT part of these results).

## Objective

Measure, on the controlled dataset, whether the production Debugger — inside
the real production Executor ↔ Debugger loop — diagnoses real pytest failures
and repairs the generated tests, without fabricating any execution.

## Dataset

Controlled debug targets from dataset v1 (hash `6c117a72e25ca8fc`):

| Sample | Failure category | Controlled defect |
|---|---|---|
| DEBUG-001 | `wrong_expected` | test asserts `add(2, 3) == 6` (real answer 5) |
| DEBUG-002 | `wrong_exception` | test expects `ValueError`, source raises `TypeError` |
| DEBUG-003 | `wrong_patch` | test patches `json.tool` — an attribute that does not exist |

## Methodology

For each sample, the buggy test is materialized with its source in an
isolated workspace and run through the **production loop**:

```
executor_node (real pytest inside an E2B sandbox)
  → route_after_execution (production router)
  → debugger_node (DebuggerLLM, fixed model, real sandbox failure output)
  → apply_fix_safely (production, test-only repairs, AST-validated)
  → executor_node again in a fresh E2B sandbox
  → … up to MAX_DEBUG_ITERATIONS = 3
```

- Every execution is a **real pytest run inside E2B** (local fallback is
  disabled when `E2B_API_KEY` is configured — sandbox errors are fatal and
  surface the real error).
- Token usage captured through an in-process recording proxy on the
  production debugger service singleton.
- No simulated execution; no fabricated results; runs with any
  quota/infra contamination would be quarantined (none occurred).

**Model:** production debugger model `nvidia/nemotron-3-super-120b-a12b:free`
(OpenRouter, temperature 0.1, max_tokens 2048, reasoning disabled).
**E2B setup:** one fresh sandbox per execution pass; source + tests uploaded
with hierarchy preserved; pytest + coverage installed in-sandbox.

## Per-sample results

| Sample | Initial failure (in E2B) | Debugger response | Repair applied | Iterations | Final result (in E2B) | Regression |
|---|---|---|---|---|---|---|
| DEBUG-001 | 1 failed / 0 errors (`test_add`) | Root cause identified: incorrect expected value (5 vs 6) | YES, confidence high | 1 | 3/3 passed, 100 % coverage | No |
| DEBUG-002 | 1 failed / 0 errors (`test_parse_port_string_raises_value_error`) | Root cause identified: wrong exception type expected | YES, confidence high | 1 | 2/2 passed, 83 % coverage | No |
| DEBUG-003 | 1 failed / 0 errors (`test_encode_uses_json_dumps`) | Root cause identified: patching a non-existent attribute | YES, confidence high | 1 | 1/1 passed, 100 % coverage | No |

Tokens (prompt + completion): DEBUG-001 441+163 · DEBUG-002 521+216 ·
DEBUG-003 509+257. Latency (full loop incl. two E2B executions):
59.7 s / 46.6 s / 43.8 s.

## Aggregated results

| Metric | Value |
|---|---|
| Repair success rate | **1.000** (3/3) |
| Test recovery rate (mean) | **1.000** |
| First-attempt repair rate | **1.000** (3/3) |
| Regression rate | **0.000** |
| Iterations (mean) | 1.0 |
| E2B sandbox passes (total) | 6 (2 per sample: failing pass + repaired pass) |
| End-to-end latency (mean) | 50.0 s |
| Token usage | 1 471 prompt + 636 completion (3 LLM calls) |
| Execution backend | `e2b_sandbox` for every pass — no local fallback occurred |
| Per failure category | `wrong_expected` 1/1 · `wrong_exception` 1/1 · `wrong_patch` 1/1 |

## Failure analysis

All three controlled defects were diagnosed with high confidence and repaired
on the first attempt: an incorrect expected constant (DEBUG-001), a wrong
expected exception type (DEBUG-002), and a wrong patch target (DEBUG-003) —
one failure category per sample, each repaired without touching production
code (test-only repairs, AST-validated before application, enforced by
`apply_fix_safely`).

## Limitations

- **n = 3 samples, one per failure category.** The 100 % repair rate must be
  read as a controlled demonstration on three failure families, not a
  statistical estimate of real-world repair success.
- The controlled defects were designed to be repairable in the test code
  only; production-code bugs are out of scope for the Debugger by design.
- Latency includes two full E2B sandbox lifecycles per sample (creation,
  upload, dependency install, execution, teardown).

## Reproducibility

```
python -m evaluation.experiments.debugger_e2b
```
Dataset: dataset v1 (hash `6c117a72e25ca8fc`), rebuildable via
`python -m evaluation.build_dataset`. Raw per-sample records:
`evaluation/results/debugger_e2b_1789850111_1138d9/`. Every sandbox pass is
additionally recorded in `logs/executor/` with execution mode
`e2b_sandbox`. No API keys are stored anywhere.
