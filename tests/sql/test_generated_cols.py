import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestGeneratedColumns:
    def test_virtual_in_order_by(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * -1) VIRTUAL)')
        db.execute("INSERT INTO t (a) VALUES (3)")
        db.execute("INSERT INTO t (a) VALUES (1)")
        db.execute("INSERT INTO t (a) VALUES (2)")
        res = db.execute('SELECT a FROM t ORDER BY b')
        assert res == [[3], [2], [1]]

    def test_virtual_in_join(self, db):
        db.execute('CREATE TABLE t1 (a INT, b INT GENERATED ALWAYS AS (a + 1) VIRTUAL)')
        db.execute('CREATE TABLE t2 (c INT)')
        db.execute("INSERT INTO t1 (a) VALUES (1), (2)")
        db.execute("INSERT INTO t2 VALUES (2), (3)")
        res = db.execute('SELECT t1.a, t2.c FROM t1 JOIN t2 ON t1.b = t2.c ORDER BY t1.a')
        assert res == [[1, 2], [2, 3]]

    def test_stored_multiple_updates(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 2) STORED)')
        db.execute("INSERT INTO t (a) VALUES (1)")
        db.execute("UPDATE t SET a = 5")
        db.execute("UPDATE t SET a = 10")
        res = db.execute('SELECT b FROM t')
        assert res == [[20]]

    def test_virtual_in_group_by(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a % 2) VIRTUAL)')
        db.execute("INSERT INTO t (a) VALUES (1), (2), (3), (4)")
        res = db.execute('SELECT b, COUNT(*) FROM t GROUP BY b')
        assert len(res) == 2
        assert [0, 2] in res
        assert [1, 2] in res

    def test_generated_with_expression(self, db):
        db.execute('CREATE TABLE t (a INT, b INT, c INT GENERATED ALWAYS AS (a + b * 2) STORED)')
        db.execute("INSERT INTO t (a, b) VALUES (1, 3)")
        res = db.execute('SELECT c FROM t')
        assert res == [[7]]

    def test_stored_with_null(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 2) STORED)')
        db.execute("INSERT INTO t (a) VALUES (5)")
        res = db.execute('SELECT * FROM t')
        assert res == [[5, 10]]

    def test_virtual_in_subquery(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a + 5) VIRTUAL)')
        db.execute("INSERT INTO t (a) VALUES (1), (2)")
        res = db.execute('SELECT x FROM (SELECT b AS x FROM t) AS sub ORDER BY x')
        assert res == [[6], [7]]

    def test_generated_both_types(self, db):
        db.execute('CREATE TABLE t (a INT, v INT GENERATED ALWAYS AS (a + 1) VIRTUAL, s INT GENERATED ALWAYS AS (v * 2) STORED)')
        db.execute("INSERT INTO t (a) VALUES (3)")
        res = db.execute('SELECT * FROM t')
        assert res == [[3, 4, 8.0]]

    def test_generated_in_where_clause(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 3) VIRTUAL)')
        db.execute("INSERT INTO t (a) VALUES (1), (2), (3)")
        res = db.execute('SELECT a FROM t WHERE b = 6')
        assert res == [[2]]
