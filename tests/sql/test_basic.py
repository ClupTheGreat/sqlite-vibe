"""End-to-end SQL integration tests."""

import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestDDL:
    def test_create_table(self, db):
        res = db.execute('CREATE TABLE t (a INT, b TEXT)')
        assert res == []

    def test_create_and_select(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        res = db.execute('SELECT * FROM t')
        assert res == []

    def test_create_if_not_exists(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('CREATE TABLE IF NOT EXISTS t (a INT)')


class TestDML:
    def test_insert_and_select(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        res = db.execute('SELECT * FROM t')
        assert res == [[1, 'hello']]

    def test_insert_multiple(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (10)')
        db.execute('INSERT INTO t VALUES (20)')
        db.execute('INSERT INTO t VALUES (30)')
        res = db.execute('SELECT * FROM t ORDER BY a')
        assert res == [[10], [20], [30]]

    def test_insert_select(self, db):
        db.execute('CREATE TABLE t1 (a INT)')
        db.execute('CREATE TABLE t2 (a INT)')
        db.execute('INSERT INTO t1 VALUES (1), (2), (3)')
        db.execute('INSERT INTO t2 SELECT * FROM t1')
        res = db.execute('SELECT * FROM t2 ORDER BY a')
        assert res == [[1], [2], [3]]

    def test_update(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'x'), (2, 'y')")
        db.execute("UPDATE t SET b = 'z' WHERE a = 1")
        res = db.execute('SELECT b FROM t ORDER BY a')
        assert res == [['z'], ['y']]

    def test_delete(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3)')
        db.execute('DELETE FROM t WHERE a = 2')
        res = db.execute('SELECT a FROM t ORDER BY a')
        assert res == [[1], [3]]


class TestSelect:
    def test_select_literal(self, db):
        res = db.execute('SELECT 1')
        assert res == [[1]]

    def test_select_literals(self, db):
        res = db.execute('SELECT 1, 2, 3')
        assert res == [[1, 2, 3]]

    def test_select_string(self, db):
        res = db.execute("SELECT 'hello'")
        assert res == [['hello']]

    def test_select_expression(self, db):
        res = db.execute('SELECT 1 + 2')
        assert res == [[3]]

    def test_select_mul(self, db):
        res = db.execute('SELECT 3 * 4')
        assert res == [[12]]

    def test_select_multiple_rows(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (10), (20), (30)')
        res = db.execute('SELECT * FROM t')
        assert len(res) == 3


class TestExpressions:
    def test_where(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3), (4)')
        res = db.execute('SELECT a FROM t WHERE a > 2')
        assert res == [[3], [4]]

    def test_and(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute('INSERT INTO t VALUES (1, 10), (2, 20), (3, 30)')
        res = db.execute('SELECT a FROM t WHERE a > 1 AND b < 30')
        assert res == [[2]]

    def test_or(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3)')
        res = db.execute('SELECT a FROM t WHERE a = 1 OR a = 3')
        assert len(res) == 2

    def test_is_null(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (NULL), (1)')
        res = db.execute('SELECT a FROM t WHERE a IS NULL')
        assert res == [[None]]

    def test_is_not_null(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (NULL), (1)')
        res = db.execute('SELECT a FROM t WHERE a IS NOT NULL')
        assert res == [[1]]


class TestOrderBy:
    def test_order_by_asc(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (3), (1), (2)')
        res = db.execute('SELECT a FROM t ORDER BY a')
        assert res == [[1], [2], [3]]

    def test_order_by_desc(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3)')
        res = db.execute('SELECT a FROM t ORDER BY a DESC')
        assert res == [[3], [2], [1]]


class TestFunctions:
    def test_length(self, db):
        res = db.execute("SELECT LENGTH('hello')")
        assert res == [[5]]

    def test_abs(self, db):
        res = db.execute('SELECT ABS(-5)')
        assert res == [[5]]

    def test_upper(self, db):
        res = db.execute("SELECT UPPER('hello')")
        assert res == [['HELLO']]

    def test_lower(self, db):
        res = db.execute("SELECT LOWER('HELLO')")
        assert res == [['hello']]


class TestTransactions:
    def test_begin_commit(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('BEGIN')
        db.execute('INSERT INTO t VALUES (1)')
        db.execute('COMMIT')
        res = db.execute('SELECT * FROM t')
        assert res == [[1]]

    def test_begin_rollback(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('BEGIN')
        db.execute('INSERT INTO t VALUES (1)')
        db.execute('ROLLBACK')
        res = db.execute('SELECT * FROM t')
        assert res == []
