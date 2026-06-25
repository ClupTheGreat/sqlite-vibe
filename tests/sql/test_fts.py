import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestFts5:
    def test_create_fts_table(self, db):
        res = db.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        assert len(res) >= 0

    def test_insert_and_match(self, db):
        db.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        db.execute("INSERT INTO t VALUES ('hello world')")
        db.execute("INSERT INTO t VALUES ('goodbye world')")
        res = db.execute("SELECT content FROM t WHERE t MATCH 'hello'")
        assert res == [['hello world']]

    def test_match_multiple_results(self, db):
        db.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        db.execute("INSERT INTO t VALUES ('apple banana')")
        db.execute("INSERT INTO t VALUES ('banana cherry')")
        db.execute("INSERT INTO t VALUES ('cherry date')")
        res = db.execute("SELECT content FROM t WHERE t MATCH 'banana' ORDER BY content")
        assert res == [['apple banana'], ['banana cherry']]

    def test_no_match(self, db):
        db.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        db.execute("INSERT INTO t VALUES ('hello world')")
        res = db.execute("SELECT content FROM t WHERE t MATCH 'nonexistent'")
        assert res == []

    def test_bm25_ranking(self, db):
        db.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        db.execute("INSERT INTO t VALUES ('hello world')")
        db.execute("INSERT INTO t VALUES ('hello there')")
        res = db.execute("SELECT content FROM t WHERE t MATCH 'hello' ORDER BY bm25(t)")
        assert len(res) == 2
