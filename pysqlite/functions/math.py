"""Math SQL function implementations."""

import math


def sin(x) -> float:
    return math.sin(float(x))


def cos(x) -> float:
    return math.cos(float(x))


def tan(x) -> float:
    return math.tan(float(x))


def asin(x) -> float:
    return math.asin(float(x))


def acos(x) -> float:
    return math.acos(float(x))


def atan(x) -> float:
    return math.atan(float(x))


def ceil(x) -> int:
    return math.ceil(float(x))


def floor(x) -> int:
    return math.floor(float(x))


def round(x) -> int:
    return round(float(x))


def log(x) -> float:
    return math.log(float(x))


def log10(x) -> float:
    return math.log10(float(x))


def sqrt(x) -> float:
    return math.sqrt(float(x))


def exp(x) -> float:
    return math.exp(float(x))


def pi() -> float:
    return math.pi


def power(x, y) -> float:
    return math.pow(float(x), float(y))


def rand() -> float:
    import random
    return random.random() * 2 - 1
