"""
Retrieval metrics for the RAG store: Recall@K, Precision@K, MRR, nDCG.

Ground truth: each dataset debug target lists the pattern `functions` for
which its stored patterns are relevant (see datasets/corpus.py PATTERN_CORPUS).
Queries are the target function names + signatures of the debug samples;
relevance is judged by pattern.function_name membership in the sample's
relevant set.
"""

import math

from evaluation.config import RETRIEVAL_K


def _dcg(relevances: list[float]) -> float:
    return sum(rel / math.log2(idx + 2) for idx, rel in enumerate(relevances))


def measure_retrieval(
    queries: list[dict],
    k: int = RETRIEVAL_K,
) -> dict:
    """
    Args:
        queries: list of {
            "function_name": str, "function_signature": str,
            "relevant": set[str]   # relevant pattern function_names
            "retrieved": list[str] # pattern function_names in ranked order
        }

    Returns Recall@K, Precision@K, MRR, nDCG (averaged over queries).
    """
    recalls, precisions, mrrs, ndcgs = [], [], [], []

    for query in queries:
        relevant = set(query["relevant"])
        retrieved = query["retrieved"][:k]

        if not relevant:
            continue

        hits = [1.0 if item in relevant else 0.0 for item in retrieved]

        recalls.append(sum(hits) / len(relevant))
        precisions.append(sum(hits) / len(retrieved) if retrieved else 0.0)

        # MRR: reciprocal rank of the first relevant result
        rr = 0.0
        for idx, hit in enumerate(hits):
            if hit:
                rr = 1.0 / (idx + 1)
                break
        mrrs.append(rr)

        # nDCG with binary gains; ideal = all relevant retrieved first
        dcg = _dcg(hits)
        ideal = [1.0] * min(len(relevant), k)
        idcg = _dcg(ideal)
        ndcgs.append(dcg / idcg if idcg else 0.0)

    def _avg(values):
        return round(sum(values) / len(values), 4) if values else None

    return {
        "k": k,
        "n_queries": len(recalls),
        "recall_at_k": _avg(recalls),
        "precision_at_k": _avg(precisions),
        "mrr": _avg(mrrs),
        "ndcg": _avg(ndcgs),
    }
