import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestAlterTable:
    def test_rename_table(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("ALTER TABLE t RENAME TO t2")
        res = db.execute("SELECT * FROM t2")
        assert res == [[1, 'hello']]

    def test_rename_column(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("ALTER TABLE t RENAME COLUMN a TO a2")
        res = db.execute("SELECT a2 FROM t")
        assert res == [[1]]

    def test_add_column(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("ALTER TABLE t ADD COLUMN c INT")
        db.execute("INSERT INTO t VALUES (2, 'world', 99)")
        res = db.execute("SELECT c FROM t WHERE a = 2")
        assert res == [[99]]

    def test_add_column_with_default(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("ALTER TABLE t ADD COLUMN c INT DEFAULT 0")
        db.execute("INSERT INTO t VALUES (2, 'world')")
        res = db.execute("SELECT c FROM t ORDER BY a")
        assert res == [[None], [None]]

    def test_drop_column(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("ALTER TABLE t DROP COLUMN b")
        res = db.execute("SELECT * FROM t")
        assert res == [[1]]

    def test_rename_nonexistent_table(self, db):
        with pytest.raises(Exception):
            db.execute("ALTER TABLE nonexistent RENAME TO t2")
