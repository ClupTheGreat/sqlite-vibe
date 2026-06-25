"""Full-text search SQL function stubs.

FTS is handled via the virtual table mechanism (fts5.py).
This module provides auxiliary functions if needed.
"""


def rank(match_info) -> float:
    return 0.0


def bm25(match_info, *weights) -> float:
    return 0.0


def highlight(match_info, col_idx: int, prefix: str = '<b>', suffix: str = '</b>') -> str:
    return ''


def snippet(match_info, col_idx: int, prefix: str = '...', suffix: str = '...',
            max_tokens: int = 10) -> str:
    return ''
