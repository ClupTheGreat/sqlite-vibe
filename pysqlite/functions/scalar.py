"""Built-in scalar SQL function implementations."""

import math
import random
import json as _json
from typing import Any


def call_datetime(name: str, args: list) -> str:
    from datetime import datetime, timedelta, timezone
    name_upper = name.upper()
    now = datetime.now(timezone.utc)
    modifiers = []
    base = None
    for i, a in enumerate(args):
        s = str(a) if a is not None else ''
        if i == 0 and s.lower() == 'now':
            base = now
        elif i == 0 and s:
            try:
                base = datetime.strptime(s, '%Y-%m-%d')
            except ValueError:
                try:
                    base = datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    base = now
        elif i > 0 or (i == 0 and base is not None and s.lower() != 'now'):
            modifiers.append(s)
    if base is None:
        base = now
    for mod in modifiers:
        parts = mod.strip().split()
        if not parts:
            continue
        op = parts[0]
        if op in ('+', '-') and len(parts) >= 2:
            try:
                amount = int(parts[0] + parts[1]) if parts[0] == '-' else int(parts[1])
            except ValueError:
                continue
            unit = parts[2].lower() if len(parts) >= 3 else 'days'
            if unit in ('days', 'day'):
                base += timedelta(days=amount)
            elif unit in ('hours', 'hour'):
                base += timedelta(hours=amount)
            elif unit in ('minutes', 'minute'):
                base += timedelta(minutes=amount)
            elif unit in ('seconds', 'second'):
                base += timedelta(seconds=amount)
            elif unit in ('months', 'month'):
                month = base.month - 1 + amount
                year = base.year + month // 12
                month = month % 12 + 1
                day = min(base.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
                base = base.replace(year=year, month=month, day=day)
            elif unit in ('years', 'year'):
                try:
                    base = base.replace(year=base.year + amount)
                except ValueError:
                    base = base.replace(year=base.year + amount, day=28)
        elif op == 'localtime':
            base = base.replace(tzinfo=None)
        elif op == 'utc':
            base = base.replace(tzinfo=timezone.utc)
        elif op == 'startofmonth':
            base = base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif op == 'startofyear':
            base = base.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    if name_upper == 'DATE':
        return base.strftime('%Y-%m-%d')
    elif name_upper == 'TIME':
        return base.strftime('%H:%M:%S')
    elif name_upper == 'DATETIME':
        return base.strftime('%Y-%m-%d %H:%M:%S')
    elif name_upper == 'JULIANDAY':
        epoch = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        delta = base - epoch
        return 2451545.0 + (delta.total_seconds() / 86400.0)
    elif name_upper == 'UNIXEPOCH':
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return int((base - epoch).total_seconds())
    elif name_upper == 'STRFTIME':
        fmt = str(args[0]) if args and args[0] is not None else '%Y-%m-%d'
        return base.strftime(fmt)
    return str(base)


def call_json_function(name: str, args: list) -> Any:
    name_upper = name.upper()
    if name_upper == 'JSON':
        return _json.dumps(args[0]) if args else 'null'
    if name_upper == 'JSON_VALID':
        if not args:
            return 0
        try:
            _json.loads(str(args[0]))
            return 1
        except (ValueError, TypeError):
            return 0
    if name_upper == 'JSON_TYPE':
        if not args:
            return 'null'
        try:
            val = _json.loads(str(args[0]))
        except (ValueError, TypeError):
            return 'null'
        if isinstance(val, dict):
            return 'object'
        if isinstance(val, list):
            return 'array'
        if isinstance(val, str):
            return 'text'
        if isinstance(val, bool):
            return 'integer'
        if isinstance(val, int):
            return 'integer'
        if isinstance(val, float):
            return 'real'
        if val is None:
            return 'null'
        return 'null'
    if name_upper == 'JSON_ARRAY_LENGTH':
        if not args:
            return 0
        try:
            val = _json.loads(str(args[0]))
        except (ValueError, TypeError):
            return 0
        return len(val) if isinstance(val, list) else 0
    if name_upper == 'JSON_EXTRACT':
        if len(args) < 2:
            return None
        try:
            val = _json.loads(str(args[0]))
        except (ValueError, TypeError):
            return None
        for path in args[1:]:
            path_str = str(path) if path is not None else ''
            if not path_str.startswith('$'):
                continue
            parts = path_str.lstrip('$').split('.')
            for part in parts:
                if not part:
                    continue
                if part.startswith('[') and part.endswith(']'):
                    try:
                        idx = int(part[1:-1])
                        val = val[idx] if isinstance(val, list) and 0 <= idx < len(val) else None
                    except (ValueError, IndexError, TypeError):
                        return None
                else:
                    val = val.get(part) if isinstance(val, dict) else None
                if val is None:
                    break
        return val
    if name_upper == 'JSON_ARRAY':
        return _json.dumps(args, separators=(',', ':'))
    if name_upper == 'JSON_OBJECT':
        obj = {}
        for i in range(0, len(args) - 1, 2):
            key = str(args[i]) if args[i] is not None else ''
            obj[key] = args[i + 1]
        return _json.dumps(obj, separators=(',', ':'))
    if name_upper in ('JSON_SET', 'JSON_INSERT', 'JSON_REPLACE'):
        if len(args) < 3:
            return _json.dumps(args[0]) if args else 'null'
        try:
            val = _json.loads(str(args[0]))
        except (ValueError, TypeError):
            return _json.dumps(args[0]) if args else 'null'
        for i in range(1, len(args) - 1, 2):
            path = str(args[i]) if args[i] is not None else ''
            new_val = args[i + 1]
            parts = path.lstrip('$').split('.')
            target = val
            if name_upper == 'JSON_INSERT':
                for part in parts[:-1]:
                    if not part:
                        break
                    if part.startswith('[') and part.endswith(']'):
                        try:
                            idx = int(part[1:-1])
                            target = target[idx] if isinstance(target, list) and 0 <= idx < len(target) else None
                        except (ValueError, IndexError, TypeError):
                            target = None
                    else:
                        target = target.get(part) if isinstance(target, dict) else None
                    if target is None:
                        break
                if target is not None and parts:
                    last = parts[-1]
                    if last.startswith('[') and last.endswith(']'):
                        try:
                            idx = int(last[1:-1])
                            if isinstance(target, list) and 0 <= idx < len(target):
                                target[idx] = new_val
                        except (ValueError, IndexError, TypeError):
                            pass
                    elif isinstance(target, dict) and last not in target:
                        pass
                continue
            for part in parts:
                if not part:
                    continue
                if part.startswith('[') and part.endswith(']'):
                    try:
                        idx = int(part[1:-1])
                        target = target[idx] if isinstance(target, list) and 0 <= idx < len(target) else None
                    except (ValueError, IndexError, TypeError):
                        target = None
                else:
                    target = target.get(part) if isinstance(target, dict) else None
            if name_upper == 'JSON_SET' and len(parts) >= 2:
                last = parts[-1]
                if last.startswith('[') and last.endswith(']'):
                    try:
                        idx = int(last[1:-1])
                        t = val
                        for p in parts[:-1]:
                            if not p:
                                continue
                            if p.startswith('[') and p.endswith(']'):
                                try:
                                    idx2 = int(p[1:-1])
                                    t = t[idx2] if isinstance(t, list) and 0 <= idx2 < len(t) else None
                                except (ValueError, IndexError, TypeError):
                                    t = None
                            else:
                                t = t.get(p) if isinstance(t, dict) else None
                        if isinstance(t, list) and 0 <= idx < len(t):
                            t[idx] = new_val
                    except (ValueError, IndexError, TypeError):
                        pass
                elif isinstance(target, dict):
                    target[last] = new_val
            elif name_upper == 'JSON_REPLACE' and target is not None:
                last = parts[-1]
                if isinstance(target, dict):
                    target[last] = new_val
        return _json.dumps(val, separators=(',', ':'))
    if name_upper == 'JSON_REMOVE':
        if len(args) < 2:
            return _json.dumps(args[0]) if args else 'null'
        try:
            val = _json.loads(str(args[0]))
        except (ValueError, TypeError):
            return _json.dumps(args[0]) if args else 'null'
        for path in args[1:]:
            path_str = str(path) if path is not None else ''
            parts = path_str.lstrip('$').split('.')
            target = val
            for part in parts[:-1]:
                if not part:
                    continue
                if part.startswith('[') and part.endswith(']'):
                    try:
                        idx = int(part[1:-1])
                        target = target[idx] if isinstance(target, list) and 0 <= idx < len(target) else None
                    except (ValueError, IndexError, TypeError):
                        target = None
                else:
                    target = target.get(part) if isinstance(target, dict) else None
            if target is not None and parts:
                last = parts[-1]
                if last.startswith('[') and last.endswith(']'):
                    try:
                        idx = int(last[1:-1])
                        if isinstance(target, list) and 0 <= idx < len(target):
                            target.pop(idx)
                    except (ValueError, IndexError, TypeError):
                        pass
                elif isinstance(target, dict) and last in target:
                    del target[last]
        return _json.dumps(val, separators=(',', ':'))
    return NotImplemented


def call_function(name: str, args: list, custom_functions: dict | None = None) -> Any:
    name_upper = name.upper()
    if custom_functions and name_upper in custom_functions:
        return custom_functions[name_upper](*args)
    if name_upper == 'ABS':
        return abs(args[0]) if args else 0
    if name_upper in ('COALESCE', 'IFNULL'):
        for a in args:
            if a is not None:
                return a
        return None
    if name_upper == 'NULLIF':
        return None if len(args) >= 2 and args[0] == args[1] else args[0]
    if name_upper == 'TYPEOF':
        if not args:
            return 'null'
        v = args[0]
        if v is None:
            return 'null'
        if isinstance(v, int) and not isinstance(v, bool):
            return 'integer'
        if isinstance(v, float):
            return 'real'
        if isinstance(v, str):
            return 'text'
        if isinstance(v, bytes):
            return 'blob'
        return 'null'
    if name_upper == 'LENGTH':
        s = str(args[0]) if args and args[0] is not None else ''
        return len(s)
    if name_upper == 'UPPER':
        return str(args[0]).upper() if args and args[0] is not None else ''
    if name_upper == 'LOWER':
        return str(args[0]).lower() if args and args[0] is not None else ''
    if name_upper == 'SUBSTR':
        if len(args) < 2:
            return ''
        s = str(args[0] or '')
        start = int(args[1] or 0)
        length = int(args[2]) if len(args) >= 3 and args[2] is not None else len(s)
        return s[start - 1:start - 1 + length] if start > 0 else s[:length]
    if name_upper == 'IFNULL':
        return args[0] if args[0] is not None else args[1] if len(args) > 1 else None
    if name_upper == 'LAST_INSERT_ROWID':
        return 0
    if name_upper == 'CHANGES':
        return 0
    if name_upper == 'TOTAL_CHANGES':
        return 0
    if name_upper == 'RANDOM':
        return random.randint(-2**63, 2**63 - 1)
    if name_upper == 'ZEROBLOB':
        n = int(args[0]) if args and args[0] is not None else 0
        return b'\x00' * n
    if name_upper == 'SIN':
        return math.sin(float(args[0])) if args else None
    if name_upper == 'COS':
        return math.cos(float(args[0])) if args else None
    if name_upper == 'TAN':
        return math.tan(float(args[0])) if args else None
    if name_upper == 'ASIN':
        return math.asin(float(args[0])) if args else None
    if name_upper == 'ACOS':
        return math.acos(float(args[0])) if args else None
    if name_upper == 'ATAN':
        return math.atan(float(args[0])) if args else None
    if name_upper == 'CEIL':
        return math.ceil(float(args[0])) if args else None
    if name_upper == 'FLOOR':
        return math.floor(float(args[0])) if args else None
    if name_upper == 'ROUND':
        return round(float(args[0])) if args else None
    if name_upper == 'LOG':
        return math.log(float(args[0])) if args else None
    if name_upper == 'LOG10':
        return math.log10(float(args[0])) if args else None
    if name_upper == 'SQRT':
        return math.sqrt(float(args[0])) if args else None
    if name_upper == 'EXP':
        return math.exp(float(args[0])) if args else None
    if name_upper == 'PI':
        return math.pi
    if name_upper in ('POWER', 'POW'):
        return math.pow(float(args[0]), float(args[1])) if len(args) >= 2 else None
    if name_upper == 'RAND':
        return random.random() * 2 - 1
    return NotImplemented
