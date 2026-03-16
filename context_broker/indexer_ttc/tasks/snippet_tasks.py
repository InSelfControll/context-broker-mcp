"""
Snippet extraction tasks for token-efficient responses.
"""

import re
from typing import Optional

import tiktoken

from context_broker.config import RESULT_MAX_TOKENS_PER_FILE, RESULT_SNIPPET_WINDOW_CHARS

QUERY_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "where",
    "what",
    "when",
    "into",
    "only",
    "show",
    "find",
    "code",
    "file",
    "files",
    "tool",
    "about",
}


def extract_query_terms(query: str) -> list[str]:
    """Extract meaningful query terms for local snippet focus."""
    terms = re.findall(r"[a-zA-Z0-9_./-]+", query.lower())
    unique_terms: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if len(term) < 3 or term in QUERY_STOPWORDS or term in seen:
            continue
        seen.add(term)
        unique_terms.append(term)
    return unique_terms[:16]


def extract_relevant_window(content: str, query_terms: list[str]) -> tuple[str, bool]:
    """Extract focused window around earliest query-term match."""
    if len(content) <= RESULT_SNIPPET_WINDOW_CHARS:
        return content, False

    start = 0
    lower_content = content.lower()
    earliest_idx: Optional[int] = None
    for term in query_terms:
        idx = lower_content.find(term)
        if idx >= 0 and (earliest_idx is None or idx < earliest_idx):
            earliest_idx = idx
    if earliest_idx is not None:
        start = max(0, earliest_idx - (RESULT_SNIPPET_WINDOW_CHARS // 3))

    end = min(len(content), start + RESULT_SNIPPET_WINDOW_CHARS)
    snippet = content[start:end]
    if start > 0:
        snippet = "...\n" + snippet
    if end < len(content):
        snippet = snippet + "\n..."
    return snippet, True


def truncate_to_token_limit(text: str, encoder: tiktoken.Encoding, token_limit: int) -> tuple[str, int, bool]:
    """Truncate text to strict token limit."""
    if token_limit <= 0:
        return "", 0, True
    token_ids = encoder.encode(text)
    if len(token_ids) <= token_limit:
        return text, len(token_ids), False
    truncated_text = encoder.decode(token_ids[:token_limit])
    return truncated_text, token_limit, True


def prepare_result_content(raw_content: str, query_terms: list[str], encoder: tiktoken.Encoding) -> tuple[str, int, bool]:
    """Prepare token-efficient snippet for response payload."""
    snippet, char_truncated = extract_relevant_window(raw_content, query_terms)
    snippet_text, snippet_tokens, token_truncated = truncate_to_token_limit(
        snippet,
        encoder,
        max(1, RESULT_MAX_TOKENS_PER_FILE),
    )
    return snippet_text, snippet_tokens, (char_truncated or token_truncated)
