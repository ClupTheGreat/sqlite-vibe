"""Unit tests for the function registry and built-in functions."""

import pytest
from pysqlite.functions import AGGREGATE_FUNCTIONS, is_aggregate_name, is_scalar_name
from pysqlite.functions.scalar import call_function
from pysqlite.functions.aggregate import compute_aggregate


class TestFunctionRegistry:
    def test_aggregate_functions_defined(self):
        assert 'COUNT' in AGGREGATE_FUNCTIONS
        assert 'SUM' in AGGREGATE_FUNCTIONS
        assert 'AVG' in AGGREGATE_FUNCTIONS

    def test_is_aggregate(self):
        assert is_aggregate_name('count')
        assert is_aggregate_name('COUNT')
        assert is_aggregate_name('Sum')
        assert not is_aggregate_name('ABS')
        assert not is_aggregate_name('unknown_func')

    def test_is_scalar(self):
        assert is_scalar_name('ABS')
        assert is_scalar_name('upper')
        assert not is_scalar_name('COUNT')


class TestScalarFunctions:
    def test_abs(self):
        assert call_function('ABS', [-5]) == 5
        assert call_function('ABS', [5]) == 5
        assert call_function('ABS', [0]) == 0

    def test_upper(self):
        assert call_function('UPPER', ['hello']) == 'HELLO'

    def test_lower(self):
        assert call_function('LOWER', ['HELLO']) == 'hello'

    def test_length(self):
        assert call_function('LENGTH', ['hello']) == 5

    def test_substr(self):
        assert call_function('SUBSTR', ['hello', 2, 3]) == 'ell'

    def test_coalesce(self):
        assert call_function('COALESCE', [None, None, 3]) == 3
        assert call_function('COALESCE', [1, None]) == 1

    def test_nullif(self):
        assert call_function('NULLIF', [5, 5]) is None
        assert call_function('NULLIF', [5, 3]) == 5

    def test_typeof(self):
        assert call_function('TYPEOF', [None]) == 'null'
        assert call_function('TYPEOF', [1]) == 'integer'
        assert call_function('TYPEOF', [1.5]) == 'real'
        assert call_function('TYPEOF', ['text']) == 'text'
        assert call_function('TYPEOF', [b'blob']) == 'blob'

    def test_zeroblob(self):
        result = call_function('ZEROBLOB', [5])
        assert result == b'\x00' * 5

    def test_math(self):
        assert call_function('SIN', [0]) == 0
        assert call_function('COS', [0]) == 1
        assert call_function('PI', []) == pytest.approx(3.14159, rel=1e-4)

    def test_unknown_returns_notimplemented(self):
        assert call_function('UNKNOWN_FUNC', [1]) is NotImplemented


class TestAggregateFunctions:
    def test_count(self):
        assert compute_aggregate('COUNT', [1, 2, 3]) == 3
        assert compute_aggregate('COUNT', [1, None, 3]) == 2

    def test_count_star(self):
        assert compute_aggregate('COUNT', [1, 2, 3], star=True) == 3

    def test_sum(self):
        assert compute_aggregate('SUM', [1, 2, 3]) == 6
        assert compute_aggregate('SUM', [1, None, 3]) == 4

    def test_avg(self):
        assert compute_aggregate('AVG', [1, 2, 3]) == 2.0

    def test_min_max(self):
        assert compute_aggregate('MIN', [3, 1, 2]) == 1
        assert compute_aggregate('MAX', [3, 1, 2]) == 3

    def test_group_concat(self):
        assert compute_aggregate('GROUP_CONCAT', ['a', 'b', 'c']) == 'a,b,c'


class TestCustomFunctions:
    def test_custom_scalar(self):
        custom = {'DOUBLE': lambda x: x * 2}
        from pysqlite.functions.scalar import call_function
        assert call_function('DOUBLE', [5], custom) == 10

    def test_custom_aggregate(self):
        class SumSq:
            def __init__(self):
                self.total = 0
            def step(self, v):
                if v is not None:
                    self.total += v * v
            def final(self):
                return self.total
        assert compute_aggregate('SUMSQ', [1, 2, 3], custom_aggregates={'SUMSQ': SumSq}) == 14
