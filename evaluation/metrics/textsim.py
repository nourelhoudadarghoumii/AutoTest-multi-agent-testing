"""
Text-similarity metrics: BLEU-4, ROUGE-L, simplified CodeBLEU.

IMPORTANT: these are TEXT-SIMILARITY metrics only. They compare generated
tests to the reference test and must NEVER be interpreted as correctness
metrics — correctness is measured by execution, coverage and mutation.

Dependency-free implementations (no nltk/evaluate).
Perplexity: not implemented — OpenRouter free endpoints do not return
logprobs; documented as future work in evaluation/README.md. GLUE is a
language-understanding benchmark and is not applicable to code generation.
"""

import ast
import math
from collections import Counter


def _tokenize(code: str) -> list[str]:
    """Simple Python tokenizer: identifiers, numbers, operators, strings."""
    tokens = []
    current = ""
    for char in code:
        if char.isalnum() or char == "_":
            current += char
        else:
            if current:
                tokens.append(current)
                current = ""
            if not char.isspace():
                tokens.append(char)
    if current:
        tokens.append(current)
    return tokens


def _ngrams(tokens: list[str], n: int) -> Counter:
    return Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def bleu4(reference: str, candidate: str) -> float:
    """Corpus-free BLEU-4 with uniform weights and simple smoothing."""
    ref_tokens, cand_tokens = _tokenize(reference), _tokenize(candidate)
    if not cand_tokens or not ref_tokens:
        return 0.0

    weights = [0.25] * 4
    log_precision = 0.0
    for n in range(1, 5):
        ref_ngrams = _ngrams(ref_tokens, n)
        cand_ngrams = _ngrams(cand_tokens, n)
        matches = sum((cand_ngrams & ref_ngrams).values())
        total = max(sum(cand_ngrams.values()), 1)
        precision = (matches + 1.0) / (total + 1.0)  # add-1 smoothing
        log_precision += weights[n - 1] * math.log(precision)

    bp = 1.0 if len(cand_tokens) >= len(ref_tokens) else math.exp(1 - len(ref_tokens) / len(cand_tokens))
    return round(bp * math.exp(log_precision), 4)


def rouge_l(reference: str, candidate: str) -> float:
    """ROUGE-L F1 over token sequences."""
    ref_tokens, cand_tokens = _tokenize(reference), _tokenize(candidate)
    if not ref_tokens or not cand_tokens:
        return 0.0

    # O(n*m) LCS — fine for test-sized code
    dp = [[0] * (len(cand_tokens) + 1) for _ in range(len(ref_tokens) + 1)]
    for i in range(1, len(ref_tokens) + 1):
        for j in range(1, len(cand_tokens) + 1):
            if ref_tokens[i - 1] == cand_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs = dp[len(ref_tokens)][len(cand_tokens)]
    precision = lcs / len(cand_tokens)
    recall = lcs / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _ast_nodes(code: str) -> Counter:
    """Node-type histogram of the AST."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return Counter()
    return Counter(type(node).__name__ for node in ast.walk(tree))


def codebleu_simplified(reference: str, candidate: str, alpha: float = 0.5) -> float:
    """
    Simplified CodeBLEU: alpha-weighted mix of token-level n-gram F1
    (averaged over 1-4 grams) and AST-node-sequence cosine similarity.
    NOT the full CodeBLEU (no data-flow matching); labeled 'simplified'.
    """
    # n-gram F1 component
    ref_tokens, cand_tokens = _tokenize(reference), _tokenize(candidate)
    ngram_f1s = []
    for n in range(1, 5):
        ref_ngrams = _ngrams(ref_tokens, n)
        cand_ngrams = _ngrams(cand_tokens, n)
        matches = sum((cand_ngrams & ref_ngrams).values())
        p = matches / sum(cand_ngrams.values()) if cand_ngrams else 0.0
        r = matches / sum(ref_ngrams.values()) if ref_ngrams else 0.0
        ngram_f1s.append(2 * p * r / (p + r) if p + r else 0.0)
    ngram_component = sum(ngram_f1s) / len(ngram_f1s)

    # AST component: cosine similarity of node histograms
    ref_ast, cand_ast = _ast_nodes(reference), _ast_nodes(candidate)
    if not ref_ast or not cand_ast:
        ast_component = 0.0
    else:
        common = set(ref_ast) & set(cand_ast)
        dot = sum(ref_ast[k] * cand_ast[k] for k in common)
        norm = math.sqrt(sum(v * v for v in ref_ast.values())) * math.sqrt(sum(v * v for v in cand_ast.values()))
        ast_component = dot / norm if norm else 0.0

    return round(alpha * ngram_component + (1 - alpha) * ast_component, 4)


def measure_text_similarity(generated: str, reference: str) -> dict:
    """All text-similarity metrics, clearly labeled as non-correctness."""
    return {
        "bleu_4": bleu4(reference, generated),
        "rouge_l": rouge_l(reference, generated),
        "codebleu_simplified": codebleu_simplified(reference, generated),
        "note": "text-similarity only — not a correctness measure",
    }
