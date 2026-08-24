"""Official RepoQA SNF evaluator, ported faithfully for the function protocol.

This module mirrors ``evalplus/repoqa`` (Apache-2.0, © 2024 EvalPlus Team)
piece by piece so numbers are comparable with published RepoQA results:

- ``sanitize_output`` — their exact markdown-fence regex, then tree-sitter
  FUNCTION_QUERY capture of the first function inside a fenced block
  (falling back to raw output / first block exactly as they do).
- ``remove_comments`` — same byte-splice algorithm over COMMENT_QUERY hits.
- ``compute_function_similarity`` — NLTK ``sentence_bleu`` with
  ``SmoothingFunction().method4`` over whitespace-token splits (identical
  formula, not a re-approximation).
- ``needle_evaluator`` — BLEU against EVERY needle function in the repo,
  best match wins; pass requires best target == ground-truth name and
  similarity >= threshold (headline threshold 0.8).

Divergences from upstream, both deliberate and documented:
1. Parsers come from this repo's pinned per-language grammar wheels via the
   modern ``Language(module.language())`` API (upstream pins the legacy
   ``tree_sitter_languages`` bundle, which conflicts with tree-sitter>=0.23).
2. Query compilation/capture failures degrade to "no functions found"
   instead of a bare ``except: pass`` around parsing only — a failed QUERY
   COMPILATION is raised loudly at first use, since silently skipping it
   would change grading semantics without anyone noticing.

Requires ``nltk`` (``uv pip install nltk``) — no corpus downloads; BLEU on
pre-split tokens needs none.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Any

HEADLINE_THRESHOLD = 0.8
THRESHOLDS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)

# Ported verbatim from evalplus/repoqa repoqa/utility.py.
FUNCTION_QUERY = {
    "python": "(function_definition name: (_)) @fdef",
    "java": "(method_declaration name: (_)) @fdef",
    "typescript": "(function_declaration name: (_)) @fdef",
    "rust": "(function_item name: (_)) @fdef",
    "cpp": (
        "(function_definition declarator: (function_declarator "
        "declarator: (identifier))) @fdef"
    ),
    "go": "(function_declaration name: (_)) @fdef",
}

COMMENT_QUERY = {
    "python": [
        "(block (expression_statement (string) @docstring))",
        "(comment) @comment",
    ],
    "java": ["(line_comment) @comment", "(block_comment) @comment"],
    "cpp": ["(comment) @comment"],
    "rust": ["(line_comment) @comment", "(block_comment) @comment"],
    "typescript": ["(comment) @comment"],
    "go": ["(comment) @comment"],
}

_LANGUAGE_MODULES = {
    "python": "tree_sitter_python",
    "java": "tree_sitter_java",
    "typescript": "tree_sitter_typescript",
    "rust": "tree_sitter_rust",
    "cpp": "tree_sitter_cpp",
    "go": "tree_sitter_go",
}


class GraderError(Exception):
    """Raised when official-protocol prerequisites or queries fail."""


@cache
def _parser_and_queries(lang: str) -> tuple[Any, Any, Any]:
    """(parser, fn_query, comment_queries[]) compiled once per language."""
    if lang not in _LANGUAGE_MODULES:
        raise GraderError(f"unsupported language for official grading: {lang!r}")
    try:
        from tree_sitter import Language, Parser, Query

        module = __import__(_LANGUAGE_MODULES[lang])
        language = Language(module.language())
        parser = Parser(language)
        try:
            fn_query = Query(language, FUNCTION_QUERY[lang])
            comment_queries = [Query(language, q) for q in COMMENT_QUERY.get(lang, [])]
        except Exception as exc:
            raise GraderError(
                f"tree-sitter query failed to compile for {lang}: {exc}"
            ) from exc
        return parser, fn_query, comment_queries
    except GraderError:
        raise
    except ImportError as exc:
        raise GraderError(
            f"missing grammar wheel {_LANGUAGE_MODULES[lang]!r} for official "
            f"grading of {lang!r}; it ships with dummyindex — reinstall it"
        ) from exc


def _captures(query: Any, root: Any) -> list[tuple[Any, str]]:
    """Normalize capture APIs across binding versions to [(node, name)]."""
    try:
        from tree_sitter import QueryCursor

        result = QueryCursor(query).captures(root)
    except ImportError:
        result = query.captures(root)
    if isinstance(result, dict):
        return [(node, name) for name, nodes in result.items() for node in nodes]
    return list(result)


def _extract_first_function(source: str, lang: str) -> str | None:
    """First function node's text per FUNCTION_QUERY, else None."""
    parser, fn_query, _ = _parser_and_queries(lang)
    block_bytes = bytes(source, "utf8")
    try:
        tree = parser.parse(block_bytes)
        for node, _name in _captures(fn_query, tree.root_node):
            return block_bytes[node.start_byte : node.end_byte].decode("utf8")
    except Exception:  # noqa: BLE001 - mirrors upstream parse tolerance
        return None
    return None


def sanitize_output(model_output: str, lang: str) -> str:
    """Port of upstream ``sanitize_output``."""
    model_output = model_output.strip()
    search_pattern = r"^```(?:\w+)?\s*\n(.*?)(?=^```)```"
    code_blocks = re.findall(search_pattern, model_output, re.DOTALL | re.MULTILINE)
    if not code_blocks:
        return model_output
    for block in code_blocks:
        extracted = _extract_first_function(block, lang)
        if extracted is not None:
            return extracted
    return code_blocks[0]


def remove_comments(source_code: str, lang: str) -> str:
    """Port of upstream byte-splice comment removal."""
    _, _, comment_queries = _parser_and_queries(lang)
    source_bytes = bytes(source_code, "utf8")
    parser, _, _ = _parser_and_queries(lang)
    tree = parser.parse(source_bytes)
    root_node = tree.root_node

    capture_list: list[tuple[Any, str]] = []
    for query in comment_queries:
        capture_list += _captures(query, root_node)

    capture_list.sort(key=lambda cap: cap[0].start_byte, reverse=True)
    for node, _ in capture_list:
        source_bytes = source_bytes[: node.start_byte] + source_bytes[node.end_byte :]
    return source_bytes.decode("utf8")


def compute_function_similarity(
    candidate_function: str, reference_function: str
) -> float:
    """NLTK smoothed-BLEU port of upstream ``compute_function_similarity``."""
    try:
        from nltk.translate.bleu_score import (  # noqa: PLC0415 - optional dep
            SmoothingFunction,
            sentence_bleu,
        )
    except ImportError as exc:
        raise GraderError(
            "the official SNF protocol requires nltk (`uv pip install nltk`)"
        ) from exc
    candidate_tokens = list(re.split(r"\s+", candidate_function.strip()))
    reference_tokens = list(re.split(r"\s+", reference_function.strip()))
    chencherry = SmoothingFunction()
    return float(
        sentence_bleu(
            [reference_tokens],
            candidate_tokens,
            smoothing_function=chencherry.method4,
        )
    )


def needle_source(repo_info: dict, needle: dict) -> str:
    """Needle function text, extracted by line slice like upstream."""
    contents = repo_info["content"]
    lines = contents[needle["path"]].split("\n")
    return "\n".join(lines[needle["start_line"] : needle["end_line"]])


def needle_evaluator(
    model_output: str,
    ground_truth: str,
    repo_info: dict,
    lang: str,
    ignore_comments: bool = False,
) -> tuple[str, float]:
    """Port of upstream ``needle_evaluator``: (best_target, best_similarity)."""
    _parser_and_queries(lang)  # validate language before any scoring work
    needles = repo_info["needles"]
    best_target = None
    best_similarity = 0.0
    sanitized = sanitize_output(model_output, lang)
    if ignore_comments:
        sanitized = remove_comments(sanitized, lang)
    for needle in needles:
        current_func = needle_source(repo_info, needle)
        if ignore_comments:
            current_func = remove_comments(current_func, lang)
        similarity = compute_function_similarity(sanitized, current_func)
        if similarity > best_similarity:
            best_similarity = similarity
            best_target = needle["name"]
    return best_target or "", best_similarity


@dataclass(frozen=True)
class SnfOfficialVerdict:
    """Result of one official-protocol grading."""

    ground_truth: str
    best_target: str
    best_similarity: float

    def passed_at(self, threshold: float = HEADLINE_THRESHOLD) -> bool:
        return (
            self.best_target == self.ground_truth and self.best_similarity >= threshold
        )

    def ladder(self) -> dict[float, bool]:
        """Pass/fail at every upstream-reported threshold."""
        return {t: self.passed_at(t) for t in THRESHOLDS}


def grade_snf_official(
    model_output: str,
    ground_truth: str,
    repo_info: dict,
    lang: str,
    ignore_comments: bool = False,
) -> SnfOfficialVerdict:
    best_target, best_similarity = needle_evaluator(
        model_output, ground_truth, repo_info, lang, ignore_comments
    )
    return SnfOfficialVerdict(
        ground_truth=ground_truth,
        best_target=best_target,
        best_similarity=best_similarity,
    )
