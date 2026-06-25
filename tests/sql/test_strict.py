"""Tests for STRICT table type enforcement."""

import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestStrict:
    def test_strict_update_preserves_type(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT) STRICT")
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("UPDATE t SET b = 'world' WHERE a = 1")
        res = db.execute('SELECT * FROM t')
        assert res == [[1, 'world']]

    def test_strict_multiple_rows_some_invalid(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT) STRICT")
        with pytest.raises(Exception, match='STRICT table'):
            db.execute("INSERT INTO t VALUES (1, 'ok'), ('not_int', 'bad'), (3, 'fine')")
        res = db.execute('SELECT * FROM t')
        assert res == [[1, 'ok']]

    def test_strict_real_type(self, db):
        db.execute("CREATE TABLE t (a REAL) STRICT")
        db.execute("INSERT INTO t VALUES (3.14)")
        with pytest.raises(Exception, match='STRICT table'):
            db.execute("INSERT INTO t VALUES ('not_a_real')")
        res = db.execute('SELECT * FROM t')
        assert res == [[3.14]]

    def test_strict_blob_type(self, db):
        db.execute("CREATE TABLE t (a BLOB) STRICT")
        db.execute("INSERT INTO t VALUES (x'0102')")
        res = db.execute('SELECT * FROM t')
        assert len(res) == 1
        assert isinstance(res[0][0], bytes)
        assert res[0][0] == b'\x01\x02'

    def test_strict_not_null_with_strict(self, db):
        db.execute("CREATE TABLE t (a INT NOT NULL, b TEXT) STRICT")
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        with pytest.raises(Exception):
            db.execute("INSERT INTO t VALUES (NULL, 'hello')")
        res = db.execute('SELECT * FROM t')
        assert res == [[1, 'hello']]

    def test_strict_select_from(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT) STRICT")
        db.execute("INSERT INTO t VALUES (10, 'ten')")
        db.execute("INSERT INTO t VALUES (20, 'twenty')")
        res = db.execute('SELECT a, b FROM t ORDER BY a')
        assert res == [[10, 'ten'], [20, 'twenty']]
