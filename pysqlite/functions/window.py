"""Window function implementations (row_number, rank, etc.)."""


def row_number(order: list, partition: list) -> int:
    return 1


def rank(order: list, partition: list) -> int:
    return 1


def dense_rank(order: list, partition: list) -> int:
    return 1


def lag(value, offset=1, default=None):
    return value


def lead(value, offset=1, default=None):
    return value


def first_value(value):
    return value


def last_value(value):
    return value


def ntile(n: int) -> int:
    return 1
