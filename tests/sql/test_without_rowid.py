"""Tests for WITHOUT ROWID table behavior."""

import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestWithoutRowid:
    def test_composite_primary_key(self, db):
        db.execute('CREATE TABLE t (a INT, b INT, c TEXT, PRIMARY KEY (a, b)) WITHOUT ROWID')
        db.execute("INSERT INTO t VALUES (1, 10, 'x')")
        db.execute("INSERT INTO t VALUES (1, 20, 'y')")
        res = db.execute('SELECT c FROM t ORDER BY a, b')
        assert len(res) == 2

    def test_insert_select_into_normal(self, db):
        db.execute('CREATE TABLE wr (pk INT PRIMARY KEY, val TEXT) WITHOUT ROWID')
        db.execute("INSERT INTO wr VALUES (1, 'a')")
        db.execute("INSERT INTO wr VALUES (2, 'b')")
        db.execute('CREATE TABLE normal (pk INT, val TEXT)')
        db.execute('INSERT INTO normal SELECT * FROM wr')
        res = db.execute('SELECT * FROM normal ORDER BY pk')
        assert res == [[1, 'a'], [2, 'b']]

    def test_update_where_complex(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b INT, c TEXT) WITHOUT ROWID')
        db.execute("INSERT INTO t VALUES (1, 10, 'x')")
        db.execute("INSERT INTO t VALUES (2, 20, 'y')")
        db.execute("INSERT INTO t VALUES (3, 30, 'z')")
        db.execute("UPDATE t SET c = 'updated' WHERE b >= 20 AND a < 3")
        res = db.execute('SELECT c FROM t ORDER BY a')
        assert res == [['x'], ['updated'], ['z']]

    def test_delete_all_without_rowid(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT) WITHOUT ROWID')
        db.execute("INSERT INTO t VALUES (1, 'one')")
        db.execute("INSERT INTO t VALUES (2, 'two')")
        db.execute('DELETE FROM t')
        res = db.execute('SELECT * FROM t')
        assert res == []

    def test_join_without_rowid(self, db):
        db.execute('CREATE TABLE t1 (a INT PRIMARY KEY, val TEXT) WITHOUT ROWID')
        db.execute("INSERT INTO t1 VALUES (1, 'foo')")
        db.execute("INSERT INTO t1 VALUES (2, 'bar')")
        db.execute('CREATE TABLE t2 (id INT, ref INT)')
        db.execute("INSERT INTO t2 VALUES (10, 1)")
        db.execute("INSERT INTO t2 VALUES (20, 2)")
        res = db.execute('SELECT t1.val, t2.id FROM t1 JOIN t2 ON t1.a = t2.ref ORDER BY t1.a')
        assert res == [['foo', 10], ['bar', 20]]

    def test_order_by_without_rowid(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b INT) WITHOUT ROWID')
        db.execute('INSERT INTO t VALUES (3, 300)')
        db.execute('INSERT INTO t VALUES (1, 100)')
        db.execute('INSERT INTO t VALUES (2, 200)')
        res = db.execute('SELECT b FROM t ORDER BY b DESC')
        assert res == [[300], [200], [100]]
