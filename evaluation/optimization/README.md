# Optimization Roadwork (NOT implemented — scaffold only)

This directory is intentionally empty of code. Per the methodology
(SCOPE → SELECT → ADAPT & ALIGN → **EVALUATE** → OPTIMIZE), optimization
work starts only after baseline and comparison experiments have produced
measured trade-offs.

## Planned optimization experiments (in order of expected value)

### 1. Prompt Optimization
Iterate on the P1/P2 structured prompts using the same fair-comparison
engine: change the prompt, keep dataset/model/environment fixed, measure
Pass@1 / coverage / mutation / hallucination / latency / tokens.

### 2. Knowledge Distillation
Use strong generated suites (high mutation score + high pass rate) from the
results archive as demonstrations for improved few-shot prompts — a
"distillation into prompts" step that requires no new infrastructure.

### 3. Local Student Model
Run a small open model locally (e.g. via Ollama/vLLM exposing an
OpenAI-compatible endpoint) as a candidate Test Writer/Debugger. The
model-comparison experiment already supports any OpenRouter-compatible
base URL through `OpenRouterService(base_url=...)`.

### 4. Quantization (FP16 / INT8 / INT4)
Applies ONLY to locally hosted student models. Remote OpenRouter models are
served by the provider — quantization is not applicable and must not be
attempted there.

### 5. Optional Pruning
Structured-pruning experiments on local student models, gated on measured
latency/quality trade-offs from the evaluation layer.

## Ground rules
- One variable per experiment; identical dataset + environment.
- Never store API keys; never auto-select winners; tables only.
- Every optimization run goes through `evaluation.run_experiment` so results
  are comparable with the baseline.
