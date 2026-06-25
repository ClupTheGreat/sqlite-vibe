"""json_each / json_tree virtual tables."""

from typing import Any
from pysqlite.virtualtables import VirtualTable, register_module


def _flatten_json(value: Any, path: str = '$', parent: str | None = None,
                  depth: int = 0, is_tree: bool = False) -> list[dict[str, Any]]:
    import json as _json
    if isinstance(value, str):
        try:
            value = _json.loads(value)
        except (_json.JSONDecodeError, ValueError):
            pass
    rows = []
    key = None
    atom_type = 'null' if value is None else type(value).__name__.lower()
    if atom_type == 'str':
        atom_type = 'text'
    elif atom_type in ('int', 'float', 'bool'):
        atom_type = 'integer' if isinstance(value, (int, bool)) else 'real'

    row = {
        'key': key,
        'value': _json.dumps(value) if isinstance(value, (dict, list)) else value,
        'type': atom_type,
        'atom': value if not isinstance(value, (dict, list)) else None,
        'id': len(rows) + 1,
        'parent': 0,
        'fullkey': path,
        'path': path.rsplit('.', 1)[0] if '.' in path else '$',
    }
    rows.append(row)

    if isinstance(value, dict):
        for k, v in value.items():
            child_path = f"{path}.{k}" if path != '$' else f"$.{k}"
            child = {
                'key': k,
                'value': _json.dumps(v) if isinstance(v, (dict, list)) else v,
                'type': 'null' if v is None else type(v).__name__.lower(),
                'atom': v if not isinstance(v, (dict, list)) else None,
                'id': len(rows) + 1,
                'parent': 0,
                'fullkey': child_path,
                'path': path,
            }
            if child['type'] == 'str':
                child['type'] = 'text'
            elif child['type'] in ('int', 'float', 'bool'):
                child['type'] = 'integer' if isinstance(v, (int, bool)) else 'real'
            rows.append(child)
            if isinstance(v, (dict, list)) and is_tree:
                rows.extend(_flatten_json(v, child_path, k, depth + 1, True))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            child_path = f"{path}[{i}]"
            child = {
                'key': i,
                'value': _json.dumps(v) if isinstance(v, (dict, list)) else v,
                'type': 'null' if v is None else type(v).__name__.lower(),
                'atom': v if not isinstance(v, (dict, list)) else None,
                'id': len(rows) + 1,
                'parent': 0,
                'fullkey': child_path,
                'path': path,
            }
            if child['type'] == 'str':
                child['type'] = 'text'
            elif child['type'] in ('int', 'float', 'bool'):
                child['type'] = 'integer' if isinstance(v, (int, bool)) else 'real'
            rows.append(child)
            if isinstance(v, (dict, list)) and is_tree:
                rows.extend(_flatten_json(v, child_path, i, depth + 1, True))
    return rows


class JsonEach(VirtualTable):
    name = 'json_each'
    module = 'json_each'
    columns = ['key', 'value', 'type', 'atom', 'id', 'parent', 'fullkey', 'path']

    def __init__(self, name: str, args: list[str], config: dict[str, Any]):
        self._rows = []
        self._idx = 0
        self._args = args

    def close(self):
        pass

    def filter(self, json_str: str | None = None):
        import json as _json
        self._idx = 0
        self._rows = []
        val = json_str or (self._args[0] if self._args else 'null')
        try:
            parsed = _json.loads(val)
            self._rows = _flatten_json(parsed, is_tree=False)
        except (_json.JSONDecodeError, ValueError):
            pass

    def next(self) -> dict[str, Any] | None:
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def reset(self):
        self._idx = 0


class JsonTree(VirtualTable):
    name = 'json_tree'
    module = 'json_tree'
    columns = ['key', 'value', 'type', 'atom', 'id', 'parent', 'fullkey', 'path']

    def __init__(self, name: str, args: list[str], config: dict[str, Any]):
        self._rows = []
        self._idx = 0
        self._args = args

    def close(self):
        pass

    def filter(self, json_str: str | None = None):
        import json as _json
        self._idx = 0
        self._rows = []
        val = json_str or (self._args[0] if self._args else 'null')
        try:
            parsed = _json.loads(val)
            self._rows = _flatten_json(parsed, is_tree=True)
        except (_json.JSONDecodeError, ValueError):
            pass

    def next(self) -> dict[str, Any] | None:
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def reset(self):
        self._idx = 0


register_module('json_each', JsonEach)
register_module('json_tree', JsonTree)
