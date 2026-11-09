# Experiment Comparison

## Test Writer

| Experiment | Model | Prompt | RAG | Pass@1 | Coverage | BranchCov | Mutation | Halluc. | Latency(s) | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| prompt_p0_1789680510_7c2d0f | cohere/north-mini-code:free | P0 | OFF | 1.0 | 100.0 | 50.0 | — | 0.0 | 3.285 | 722.5 |
| prompt_p1_1789680556_8d4eeb | cohere/north-mini-code:free | P1 | OFF | 1.0 | 100.0 | 50.0 | — | 0.0 | 3.18 | 518 |
| prompt_p2_1789680587_5f1029 | cohere/north-mini-code:free | P2 | OFF | 1.0 | 100.0 | 50.0 | — | 0.0 | 3.15 | 686.5 |
| prompt_p3_1789680619_694bcf | cohere/north-mini-code:free | P3 | OFF | 1.0 | 100.0 | 50.0 | — | 0.0 | 3.135 | 683.5 |

_Text-similarity metrics (BLEU/ROUGE/CodeBLEU) are excluded from this table: they are similarity measures, never correctness measures._