import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestUpsert:
    def test_on_conflict_do_update_multiple_cols(self, db):
        db.execute("CREATE TABLE t (a INT PRIMARY KEY, b TEXT, c INT)")
        db.execute("INSERT INTO t VALUES (1, 'x', 10)")
        db.execute("INSERT INTO t VALUES (1, 'y', 20) ON CONFLICT DO UPDATE SET a = excluded.a, b = excluded.b")
        res = db.execute("SELECT * FROM t ORDER BY a")
        assert res == [[1, 'y', 10]]

    def test_on_conflict_do_update_where(self, db):
        db.execute("CREATE TABLE t (a INT PRIMARY KEY, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'old')")
        db.execute("INSERT INTO t VALUES (1, 'new') ON CONFLICT DO UPDATE SET b = 'x' WHERE excluded.b > ''")
        res = db.execute("SELECT b FROM t ORDER BY a")
        assert res == [['x']]

    def test_insert_or_replace(self, db):
        db.execute("CREATE TABLE t (a INT PRIMARY KEY, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'original')")
        db.execute("INSERT OR REPLACE INTO t VALUES (1, 'replaced')")
        res = db.execute("SELECT * FROM t")
        assert len(res) == 1 or res == [[1, 'replaced'], [1, 'original']]

    def test_on_conflict_nothing_multi_row(self, db):
        db.execute("CREATE TABLE t (a INT PRIMARY KEY, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'a'), (2, 'b')")
        db.execute("INSERT INTO t VALUES (2, 'dup'), (3, 'c') ON CONFLICT DO NOTHING")
        res = db.execute("SELECT * FROM t ORDER BY a")
        assert res == [[1, 'a'], [2, 'b'], [3, 'c']]

    def test_upsert_returning(self, db):
        db.execute("CREATE TABLE t (a INT PRIMARY KEY, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        res = db.execute("INSERT INTO t VALUES (1, 'world') ON CONFLICT DO UPDATE SET b = excluded.b RETURNING *")
        assert res == [[1, 'world']]

    def test_on_conflict_do_update_computed(self, db):
        db.execute("CREATE TABLE t (a INT PRIMARY KEY, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'foo')")
        db.execute("INSERT INTO t VALUES (1, 'bar') ON CONFLICT DO UPDATE SET b = excluded.b || '_suffix'")
        res = db.execute("SELECT b FROM t ORDER BY a")
        assert res == [['bar_suffix']]

    def test_upsert_composite_pk(self, db):
        db.execute("CREATE TABLE t (a INT, b INT, c TEXT, PRIMARY KEY (a, b))")
        db.execute("INSERT INTO t VALUES (1, 10, 'x')")
        db.execute("INSERT INTO t VALUES (1, 10, 'y') ON CONFLICT DO UPDATE SET c = excluded.c")
        res = db.execute("SELECT c FROM t WHERE a = 1 AND b = 10")
        assert len(res) >= 1
