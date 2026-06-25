import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestCreateTable:
    def test_create_if_not_exists(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("CREATE TABLE IF NOT EXISTS t (a INT)")

    def test_create_temp_table(self, db):
        res = db.execute("CREATE TEMP TABLE t (a INT)")
        assert res == []

    def test_create_with_defaults_parses(self, db):
        res = db.execute("CREATE TABLE t (a INT DEFAULT 42)")
        db.execute("INSERT INTO t VALUES (1)")
        r = db.execute("SELECT * FROM t")
        assert r == [[1]]


class TestCreateIndex:
    def test_create_index(self, db):
        db.execute("CREATE TABLE t (a INT)")
        res = db.execute("CREATE INDEX idx_a ON t(a)")
        assert res == []

    def test_create_index_multi_column(self, db):
        db.execute("CREATE TABLE t (a INT, b INT)")
        res = db.execute("CREATE INDEX idx_ab ON t(a, b)")
        assert res == []

    def test_create_unique_index(self, db):
        db.execute("CREATE TABLE t (a INT)")
        res = db.execute("CREATE UNIQUE INDEX idx ON t(a)")
        assert res == []

    def test_drop_index(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("CREATE INDEX idx ON t(a)")
        res = db.execute("DROP INDEX idx")
        assert res == []


class TestDropTable:
    def test_drop_table(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1)")
        res = db.execute("DROP TABLE t")
        assert res == []

    def test_drop_if_exists(self, db):
        db.execute("DROP TABLE IF EXISTS nonexistent")


class TestSchemaQuery:
    def test_table_info(self, db):
        db.execute("CREATE TABLE t (a INT PRIMARY KEY, b TEXT NOT NULL DEFAULT 'x')")
        res = db.execute("PRAGMA table_info('t')")
        assert len(res) == 2
        assert res[0][1] == 'a'
        assert res[1][1] == 'b'
