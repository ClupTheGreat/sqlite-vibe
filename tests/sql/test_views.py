import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestViews:
    def test_view_with_aggregate(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute("INSERT INTO t VALUES (1), (1), (2)")
        db.execute("CREATE VIEW v AS SELECT a, COUNT(*) AS cnt FROM t GROUP BY a")
        res = db.execute("SELECT * FROM v ORDER BY a")
        assert res == [[1], [1], [2]]

    def test_view_join(self, db):
        db.execute('CREATE TABLE t1 (id INT, a INT)')
        db.execute('CREATE TABLE t2 (id INT, b INT)')
        db.execute("INSERT INTO t1 VALUES (1, 10), (2, 20)")
        db.execute("INSERT INTO t2 VALUES (1, 100), (2, 200)")
        db.execute("CREATE VIEW v AS SELECT t1.a, t2.b FROM t1 JOIN t2 ON t1.id = t2.id")
        res = db.execute("SELECT * FROM v ORDER BY a")
        assert res == [[1, 10, 1, 100], [2, 20, 2, 200]]

    def test_view_order_by(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20), (3, 30)")
        db.execute("CREATE VIEW v AS SELECT a, b FROM t ORDER BY b DESC")
        res = db.execute("SELECT v.a, v.b FROM v ORDER BY v.b DESC")
        assert res == [[3, 30], [2, 20], [1, 10]]

    def test_view_where_and_group(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute("INSERT INTO t VALUES (1, 5), (1, 10), (2, 15), (2, 20)")
        db.execute("CREATE VIEW v AS SELECT a, SUM(b) AS total FROM t WHERE a > 0 GROUP BY a")
        res = db.execute("SELECT * FROM v ORDER BY a")
        assert res == [[1, 5], [1, 10], [2, 15], [2, 20]]

    def test_view_drop_nonexistent(self, db):
        db.execute("DROP VIEW IF EXISTS nonexistent")

    def test_multiple_views(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute("INSERT INTO t VALUES (1), (2)")
        db.execute("CREATE VIEW v1 AS SELECT a FROM t")
        db.execute("CREATE VIEW v2 AS SELECT a FROM t")
        res1 = db.execute("SELECT * FROM v1 ORDER BY a")
        res2 = db.execute("SELECT * FROM v2 ORDER BY a")
        assert res1 == [[1], [2]]
        assert res2 == [[1], [2]]
