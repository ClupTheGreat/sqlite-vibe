"""Regression tests — bug reproduction cases."""

import pytest
from pysqlite import Database


def ep(db, sql, params=None):
    if params is not None:
        return db.execute_params(sql, params)
    return db.execute(sql)


class TestRegression:
    def test_empty_table_select(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT)')
        res = db.execute('SELECT * FROM t')
        assert res == []

    def test_null_insert_and_select(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute('INSERT INTO t VALUES (NULL, NULL)')
        res = db.execute('SELECT * FROM t')
        assert res == [[None, None]]

    def test_multiple_where_conditions(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT, b INT, c INT)')
        db.execute('INSERT INTO t VALUES (1, 2, 3)')
        db.execute('INSERT INTO t VALUES (4, 5, 6)')
        db.execute('INSERT INTO t VALUES (7, 8, 9)')
        res = db.execute('SELECT * FROM t WHERE a > 1 AND b > 4')
        assert res == [[4, 5, 6], [7, 8, 9]]

    def test_order_by_desc_nulls_last(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (NULL)')
        db.execute('INSERT INTO t VALUES (1)')
        db.execute('INSERT INTO t VALUES (2)')
        res = db.execute('SELECT a FROM t ORDER BY a DESC NULLS LAST')
        assert res == [[2], [1], [None]]

    def test_delete_where_eq(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT)')
        for i in range(10):
            db.execute(f'INSERT INTO t VALUES ({i})')
        db.execute('DELETE FROM t WHERE a = 5')
        res = db.execute('SELECT count(*) FROM t')
        assert res[0][0] == 9

    def test_update_all_rows(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'x')")
        db.execute("INSERT INTO t VALUES (2, 'y')")
        db.execute("UPDATE t SET b = 'z'")
        res = db.execute('SELECT b FROM t ORDER BY a')
        assert res == [['z'], ['z']]

    def test_where_with_null_comparison(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (NULL)')
        db.execute('INSERT INTO t VALUES (1)')
        res = db.execute('SELECT * FROM t WHERE a IS NULL')
        assert res == [[None]]

    def test_where_gt(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT)')
        for i in range(5):
            db.execute(f'INSERT INTO t VALUES ({i})')
        res = db.execute('SELECT * FROM t WHERE a > 2')
        assert res == [[3], [4]]
