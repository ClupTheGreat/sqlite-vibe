import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestInsert:
    def test_insert_default_values(self, db):
        db.execute("CREATE TABLE t (a INT DEFAULT 0, b TEXT DEFAULT 'x')")
        db.execute("INSERT INTO t DEFAULT VALUES")
        res = db.execute("SELECT * FROM t")
        assert res == [[None, None]]

    def test_insert_with_column_list(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT, c INT)")
        db.execute("INSERT INTO t (a, b) VALUES (42, 'hello')")
        res = db.execute("SELECT * FROM t")
        assert len(res) == 1
        assert res[0] == [42, 'hello', None]

    def test_insert_values_multi_row(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'x'), (2, 'y')")
        res = db.execute("SELECT a, b FROM t ORDER BY a")
        assert res == [[1, 'x'], [2, 'y']]
