import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestCTEs:
    def test_simple_cte(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20), (3, 30)")
        res = db.execute("WITH cte AS (SELECT a, b FROM t) SELECT * FROM cte ORDER BY a")
        assert res == [[1, 10], [2, 20], [3, 30]]

    def test_cte_with_column_list(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20)")
        res = db.execute("WITH cte(x, y) AS (SELECT a, b FROM t) SELECT * FROM cte ORDER BY x")
        assert res == [[1, 10], [2, 20]]

    def test_cte_where_filter(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20), (3, 30)")
        res = db.execute("WITH cte AS (SELECT * FROM t) SELECT * FROM cte WHERE a > 1 ORDER BY a")
        assert res == [[2, 20], [3, 30]]

    def test_cte_expression(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        res = db.execute("WITH cte AS (SELECT a * 2 AS d FROM t) SELECT d FROM cte ORDER BY d")
        assert res == [[2], [4], [6]]

    def test_cte_join(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20)")
        db.execute("CREATE TABLE t2 (a INT, c INT)")
        db.execute("INSERT INTO t2 VALUES (1, 100), (2, 200)")
        res = db.execute("WITH cte AS (SELECT a, b FROM t) SELECT cte.a, cte.b, t2.a, t2.c FROM cte, t2 WHERE cte.a = t2.a ORDER BY cte.a")
        assert res == [[1, 10, 1, 100], [2, 20, 2, 200]]

    def test_multiple_ctes(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute("INSERT INTO t VALUES (1), (2)")
        res = db.execute("WITH cte1 AS (SELECT a FROM t), cte2 AS (SELECT a FROM t) SELECT * FROM cte1 ORDER BY a")
        assert res == [[1], [2]]

    def test_cte_in_insert_select(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        db.execute("CREATE TABLE t2 (a INT)")
        db.execute("WITH cte AS (SELECT * FROM t) INSERT INTO t2 SELECT * FROM cte")
        res = db.execute("SELECT * FROM t2 ORDER BY a")
        assert res == [[1], [2], [3]]
