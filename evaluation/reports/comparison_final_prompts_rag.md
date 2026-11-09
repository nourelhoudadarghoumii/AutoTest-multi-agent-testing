# Experiment Comparison

## Test Writer

| Experiment | Model | Prompt | RAG | Pass@1 | Coverage | BranchCov | Mutation | Halluc. | Latency(s) | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline_1789680234_e97dc4 | cohere/north-mini-code:free | P0 | OFF | 1.0 | 100.0 | 50.0 | — | 0.0697 | 3.645 | 721.5 |
| baseline_1789681278_877bff | cohere/north-mini-code:free | P0 | OFF | 0.6667 | 96.2325 | 87.3608 | 1.0 | 0.0 | 4.5992 | 856.8333 |
| prompt_p0_1789680510_7c2d0f | cohere/north-mini-code:free | P0 | OFF | 1.0 | 100.0 | 50.0 | — | 0.0 | 3.285 | 722.5 |
| prompt_p0_1789728854_98e7e4 | cohere/north-mini-code:free | P0 | OFF | 0.75 | 96.2325 | 87.3608 | 1.0 | 0.0 | 3.2833 | 866.4167 |
| prompt_p1_1789680556_8d4eeb | cohere/north-mini-code:free | P1 | OFF | 1.0 | 100.0 | 50.0 | — | 0.0 | 3.18 | 518 |
| prompt_p1_1789752597_a96eb2 | cohere/north-mini-code:free | P1 | OFF | 0.75 | 92.675 | 81.9442 | 1.0 | 0.0 | 1.6475 | 706.25 |
| prompt_p2_1789680587_5f1029 | cohere/north-mini-code:free | P2 | OFF | 1.0 | 100.0 | 50.0 | — | 0.0 | 3.15 | 686.5 |
| prompt_p2_1789758263_3f7aee | cohere/north-mini-code:free | P2 | OFF | 0.75 | 96.9575 | 88.1942 | 0.4545 | 0.0 | 1.9675 | 804.25 |
| prompt_p3_1789680619_694bcf | cohere/north-mini-code:free | P3 | OFF | 1.0 | 100.0 | 50.0 | — | 0.0 | 3.135 | 683.5 |
| prompt_p3_1789776746_63c4d9 | cohere/north-mini-code:free | P3 | OFF | 0.75 | 96.9575 | 88.1942 | 0.1818 | 0.0 | 4.0875 | 810.9167 |
| rag_off_1789777201_2b1cd7 | cohere/north-mini-code:free | P3 | OFF | 0.75 | 96.9575 | 88.1942 | 0.1818 | 0.0 | 4.0075 | 814.8333 |
| rag_on_1789777613_9f485e | cohere/north-mini-code:free | P3 | ON | 0.75 | 96.9575 | 88.1942 | 0.1818 | 0.0 | 4.13 | 930.25 |

## Debugger

| Experiment | Model | RepairRate | Recovery | FirstAttempt | Regression | Iterations | Latency(s) |
|---|---|---|---|---|---|---|---|
| debugger_1789680285_bf3d14 | nvidia/nemotron-3-super-120b-a12b:free | 1.0 | 1.0 | 1.0 | 0.0 | 1 | 7.57 |

_Text-similarity metrics (BLEU/ROUGE/CodeBLEU) are excluded from this table: they are similarity measures, never correctness measures._