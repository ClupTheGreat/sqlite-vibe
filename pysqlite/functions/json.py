"""JSON SQL function implementations."""

from pysqlite.functions.scalar import call_json_function


def json_valid(val) -> int:
    return call_json_function('JSON_VALID', [val])


def json_type(val) -> str:
    return call_json_function('JSON_TYPE', [val])


def json_array_length(val) -> int:
    return call_json_function('JSON_ARRAY_LENGTH', [val])


def json_extract(val, *paths):
    return call_json_function('JSON_EXTRACT', [val, *paths])


def json_array(*args):
    return call_json_function('JSON_ARRAY', list(args))


def json_object(*args):
    return call_json_function('JSON_OBJECT', list(args))


def json_set(val, *pairs):
    return call_json_function('JSON_SET', [val, *pairs])


def json_insert(val, *pairs):
    return call_json_function('JSON_INSERT', [val, *pairs])


def json_replace(val, *pairs):
    return call_json_function('JSON_REPLACE', [val, *pairs])


def json_remove(val, *paths):
    return call_json_function('JSON_REMOVE', [val, *paths])
