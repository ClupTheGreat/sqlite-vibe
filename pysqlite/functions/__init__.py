"""Function registry for built-in SQL functions."""

from pysqlite.functions.scalar import call_function as call_scalar
from pysqlite.functions.aggregate import compute_aggregate

AGGREGATE_FUNCTIONS = frozenset({
    'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'GROUP_CONCAT',
    'TOTAL', 'JSON_GROUP_ARRAY', 'JSON_GROUP_OBJECT',
})

SCALAR_FUNCTIONS = frozenset({
    'ABS', 'UPPER', 'LOWER', 'LENGTH', 'SUBSTR',
    'COALESCE', 'IFNULL', 'NULLIF', 'TYPEOF',
    'LAST_INSERT_ROWID', 'CHANGES', 'TOTAL_CHANGES',
    'RANDOM', 'ZEROBLOB',
    'SIN', 'COS', 'TAN', 'ASIN', 'ACOS', 'ATAN',
    'CEIL', 'FLOOR', 'ROUND', 'LOG', 'LOG10', 'SQRT',
    'EXP', 'PI', 'POWER', 'POW', 'RAND',
    'DATE', 'TIME', 'DATETIME', 'JULIANDAY', 'STRFTIME', 'UNIXEPOCH',
    'JSON', 'JSON_VALID', 'JSON_TYPE', 'JSON_ARRAY_LENGTH',
    'JSON_EXTRACT', 'JSON_ARRAY', 'JSON_OBJECT',
    'JSON_SET', 'JSON_INSERT', 'JSON_REPLACE', 'JSON_REMOVE',
})


def is_aggregate_name(name: str) -> bool:
    return name.upper() in AGGREGATE_FUNCTIONS


def is_scalar_name(name: str) -> bool:
    return name.upper() in SCALAR_FUNCTIONS
