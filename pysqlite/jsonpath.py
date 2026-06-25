"""JSONPath parser and evaluator for SQLite JSON functions.

Supports the subset used by SQLite:
  $            root
  .key         object member
  ."key"       quoted object member
  [N]          array index
  [#-1]        array index from end
  [*]          wildcard (all array elements / all object members)
"""

import re
from typing import Any


class PathToken:
    pass


class Root(PathToken):
    def __repr__(self):
        return 'Root()'


class Member(PathToken):
    def __init__(self, key: str):
        self.key = key

    def __repr__(self):
        return f'Member({self.key!r})'


class ArrayIndex(PathToken):
    def __init__(self, index: int):
        self.index = index

    def __repr__(self):
        return f'ArrayIndex({self.index})'


class ArrayWildcard(PathToken):
    def __repr__(self):
        return 'ArrayWildcard()'


class MemberWildcard(PathToken):
    def __repr__(self):
        return 'MemberWildcard()'


_TOKEN_RE = re.compile(r"""
    \.(?:"([^"]*)"|'([^']*)'|([a-zA-Z_][a-zA-Z0-9_]*))   # .key ."key" .'key'
    |\[(-?\d+|\*)\]                                            # [N] [*]
    |\$                                                        # root
""", re.VERBOSE)


def parse_path(path_str: str) -> list[PathToken]:
    tokens = []
    pos = 0
    s = path_str.strip()
    if not s:
        return [Root()]
    if s[0] != '$':
        s = '$' + s
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            raise ValueError(f'Invalid JSON path at position {pos}: {s[pos:]!r}')
        if m.group(0) == '$':
            tokens.append(Root())
        elif m.group(1) is not None:
            tokens.append(Member(m.group(1)))
        elif m.group(2) is not None:
            tokens.append(Member(m.group(2)))
        elif m.group(3) is not None:
            tokens.append(Member(m.group(3)))
        elif m.group(4) is not None:
            raw = m.group(4)
            if raw == '*':
                tokens.append(ArrayWildcard())
            else:
                tokens.append(ArrayIndex(int(raw)))
        pos = m.end()
    if not tokens:
        tokens.append(Root())
    return tokens


def evaluate_path(data: Any, tokens: list[PathToken]) -> list[Any]:
    results = [data]
    for token in tokens:
        if isinstance(token, Root):
            continue
        next_results = []
        for item in results:
            if isinstance(token, Member):
                if isinstance(item, dict):
                    key = token.key
                    if key in item:
                        next_results.append(item[key])
            elif isinstance(token, MemberWildcard):
                if isinstance(item, dict):
                    next_results.extend(item.values())
            elif isinstance(token, ArrayIndex):
                if isinstance(item, list):
                    idx = token.index
                    if idx < 0:
                        idx = len(item) + idx
                    if 0 <= idx < len(item):
                        next_results.append(item[idx])
            elif isinstance(token, ArrayWildcard):
                if isinstance(item, list):
                    next_results.extend(item)
        results = next_results
    return results


def json_path_extract(data: Any, path_str: str) -> Any:
    tokens = parse_path(path_str)
    results = evaluate_path(data, tokens)
    if len(results) == 1:
        return results[0]
    return None


def json_path_set(data: Any, path_str: str, value: Any, mode: str = 'set') -> Any:
    tokens = parse_path(path_str)
    return _json_path_set_recursive(data, tokens, 0, value, mode)


def _json_path_set_recursive(data: Any, tokens: list[PathToken], idx: int,
                             value: Any, mode: str) -> Any:
    if idx >= len(tokens):
        return value
    token = tokens[idx]
    if isinstance(token, Root):
        return _json_path_set_recursive(data, tokens, idx + 1, value, mode)
    if isinstance(token, Member):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        key = token.key
        if idx == len(tokens) - 1:
            if mode == 'set' or (mode == 'insert' and key not in result) or \
               (mode == 'replace' and key in result):
                result[key] = value
        elif key in result:
            result[key] = _json_path_set_recursive(
                result[key], tokens, idx + 1, value, mode)
        return result
    if isinstance(token, ArrayIndex):
        if not isinstance(data, list):
            return data
        result = list(data)
        arr_idx = token.index
        if arr_idx < 0:
            arr_idx = len(result) + arr_idx
        if 0 <= arr_idx < len(result):
            if idx == len(tokens) - 1:
                if mode != 'insert' or arr_idx >= len(data):
                    result[arr_idx] = value
            else:
                result[arr_idx] = _json_path_set_recursive(
                    result[arr_idx], tokens, idx + 1, value, mode)
        return result
    return data


def json_path_remove(data: Any, path_str: str) -> Any:
    tokens = parse_path(path_str)
    return _json_path_remove_recursive(data, tokens, 0)


def _json_path_remove_recursive(data: Any, tokens: list[PathToken], idx: int) -> Any:
    if idx >= len(tokens):
        return data
    token = tokens[idx]
    if isinstance(token, Root):
        return _json_path_remove_recursive(data, tokens, idx + 1)
    if isinstance(token, Member):
        if not isinstance(data, dict):
            return data
        if idx == len(tokens) - 1:
            result = dict(data)
            result.pop(token.key, None)
            return result
        result = dict(data)
        if token.key in result:
            result[token.key] = _json_path_remove_recursive(
                result[token.key], tokens, idx + 1)
        return result
    if isinstance(token, ArrayIndex):
        if not isinstance(data, list):
            return data
        if idx == len(tokens) - 1:
            result = list(data)
            arr_idx = token.index
            if arr_idx < 0:
                arr_idx = len(result) + arr_idx
            if 0 <= arr_idx < len(result):
                result.pop(arr_idx)
            return result
        result = list(data)
        arr_idx = token.index
        if arr_idx < 0:
            arr_idx = len(result) + arr_idx
        if 0 <= arr_idx < len(result):
            result[arr_idx] = _json_path_remove_recursive(
                result[arr_idx], tokens, idx + 1)
        return result
    return data


def json_type_of(data: Any, path_str: str = '$') -> str | None:
    tokens = parse_path(path_str)
    results = evaluate_path(data, tokens)
    if len(results) != 1:
        return None
    return _pytype_to_json_type(results[0])


def _pytype_to_json_type(val: Any) -> str:
    if val is None:
        return 'null'
    if isinstance(val, bool):
        return 'true' if val else 'false'
    if isinstance(val, int):
        return 'integer'
    if isinstance(val, float):
        return 'real'
    if isinstance(val, str):
        return 'text'
    if isinstance(val, list):
        return 'array'
    if isinstance(val, dict):
        return 'object'
    return 'null'


def json_array_length_of(data: Any, path_str: str = '$') -> int | None:
    tokens = parse_path(path_str)
    results = evaluate_path(data, tokens)
    if len(results) != 1:
        return None
    val = results[0]
    if isinstance(val, list):
        return len(val)
    return None
