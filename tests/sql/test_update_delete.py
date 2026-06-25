import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestUpdate:
    def test_update_all(self, db):
        db.execute("CREATE TABLE t (a INT, b INT)")
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20), (3, 30)")
        db.execute("UPDATE t SET b = 99")
        res = db.execute("SELECT * FROM t ORDER BY a")
        assert res == [[1, 99], [2, 99], [3, 99]]

    def test_update_multiple_columns(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT, c INT)")
        db.execute("INSERT INTO t VALUES (1, 'x', 10)")
        db.execute("UPDATE t SET b = 'y', c = 20 WHERE a = 1")
        res = db.execute("SELECT * FROM t")
        assert res == [[1, 'y', 20]]

    def test_update_no_match(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'x')")
        db.execute("UPDATE t SET b = 'y' WHERE a = 99")
        res = db.execute("SELECT b FROM t")
        assert res == [['x']]


class TestDelete:
    def test_delete_all(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        db.execute("DELETE FROM t")
        res = db.execute("SELECT * FROM t")
        assert res == []

    def test_delete_where_single(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        db.execute("DELETE FROM t WHERE a = 2")
        res = db.execute("SELECT a FROM t ORDER BY a")
        assert res == [[1], [3]]

    def test_delete_where_multiple(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3), (4), (5)")
        db.execute("DELETE FROM t WHERE a > 3")
        res = db.execute("SELECT a FROM t ORDER BY a")
        assert res == [[1], [2], [3]]

    def test_delete_no_match(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1)")
        db.execute("DELETE FROM t WHERE a = 99")
        res = db.execute("SELECT * FROM t")
        assert res == [[1]]
