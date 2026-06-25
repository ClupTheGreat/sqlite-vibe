"""Date/time SQL function implementations."""

from pysqlite.functions.scalar import call_datetime


def date(*args) -> str:
    return call_datetime('DATE', list(args))


def time(*args) -> str:
    return call_datetime('TIME', list(args))


def datetime(*args) -> str:
    return call_datetime('DATETIME', list(args))


def julianday(*args) -> float:
    return call_datetime('JULIANDAY', list(args))


def strftime(*args) -> str:
    return call_datetime('STRFTIME', list(args))


def unixepoch(*args) -> int:
    return call_datetime('UNIXEPOCH', list(args))
