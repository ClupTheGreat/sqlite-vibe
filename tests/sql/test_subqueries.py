import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestFromSubquery:
    def test_from_subquery(self, db):
        db.execute("CREATE TABLE t (a INT, b INT)")
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20), (3, 30)")
        res = db.execute("SELECT * FROM (SELECT a, b FROM t) AS sub WHERE a > 1 ORDER BY a")
        assert res == [[2, 20], [3, 30]]

    def test_from_subquery_with_expression(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        res = db.execute("SELECT x FROM (SELECT a * 2 AS x FROM t) AS sub ORDER BY x")
        assert res == [[2], [4], [6]]
