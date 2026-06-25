"""Built-in aggregate SQL function implementations."""

import json as _json
from typing import Any


def compute_aggregate(name: str, values: list, star: bool = False,
                      custom_aggregates: dict | None = None) -> Any:
    name_upper = name.upper()
    if custom_aggregates and name_upper in custom_aggregates:
        agg_cls = custom_aggregates[name_upper]
        instance = agg_cls()
        for v in values:
            if hasattr(instance, 'step'):
                instance.step(v)
        return instance.final() if hasattr(instance, 'final') else None
    if name_upper == 'COUNT':
        if star:
            return len(values)
        return sum(1 for v in values if v is not None)
    if name_upper in ('SUM', 'TOTAL'):
        total = 0
        for v in values:
            if isinstance(v, (int, float)):
                total += v
        return total
    if name_upper == 'AVG':
        total = 0
        count = 0
        for v in values:
            if isinstance(v, (int, float)):
                total += v
                count += 1
        return total / count if count else 0
    if name_upper == 'MIN':
        non_null = [v for v in values if v is not None]
        return min(non_null) if non_null else None
    if name_upper == 'MAX':
        non_null = [v for v in values if v is not None]
        return max(non_null) if non_null else None
    if name_upper == 'GROUP_CONCAT':
        separator = ','
        if values and isinstance(values[0], tuple):
            items = [str(v[0]) for v in values if v[0] is not None]
            if values[0] and len(values[0]) > 1 and values[0][1] is not None:
                separator = str(values[0][1])
        else:
            items = [str(v) for v in values if v is not None]
        return separator.join(items) if items else None
    if name_upper == 'JSON_GROUP_ARRAY':
        items = [v for v in values if v is not None]
        return _json.dumps(items, separators=(',', ':'))
    if name_upper == 'JSON_GROUP_OBJECT':
        obj = {}
        for v in values:
            if isinstance(v, tuple) and len(v) >= 2:
                key = str(v[0]) if v[0] is not None else None
                if key is not None:
                    obj[key] = v[1]
        return _json.dumps(obj, separators=(',', ':')) if obj else '{}'
    return len(values)
