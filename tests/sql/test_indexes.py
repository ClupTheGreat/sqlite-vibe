import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestCreateIndex:
    def test_create_simple_index(self, db):
        db.execute("CREATE TABLE t (a INT)")
        res = db.execute("CREATE INDEX idx ON t(a)")
        assert res == []

    def test_index_list_pragma(self, db):
        db.execute("CREATE TABLE t (a INT, b INT)")
        db.execute("CREATE INDEX idx_a ON t(a)")
        db.execute("CREATE INDEX idx_b ON t(b)")
        res = db.execute("PRAGMA index_list('t')")
        assert len(res) == 2
        names = {r[1] for r in res}
        assert 'idx_a' in names
        assert 'idx_b' in names

    def test_index_info_pragma(self, db):
        db.execute("CREATE TABLE t (a INT, b INT)")
        db.execute("CREATE INDEX idx_ab ON t(a, b)")
        res = db.execute("PRAGMA index_info('idx_ab')")
        assert len(res) == 2
        assert res[0][2] == 'a'
        assert res[1][2] == 'b'

    def test_unique_index_allows_null_duplicates(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("CREATE UNIQUE INDEX idx ON t(a)")
        db.execute("INSERT INTO t VALUES (NULL)")
        db.execute("INSERT INTO t VALUES (NULL)")
        res = db.execute("SELECT * FROM t")
        assert len(res) == 2

    def test_drop_index(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("CREATE INDEX idx ON t(a)")
        db.execute("DROP INDEX idx")
