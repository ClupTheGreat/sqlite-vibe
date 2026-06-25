import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestSelectStar:
    def test_select_star(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'x')")
        res = db.execute("SELECT * FROM t")
        assert res == [[1, 'x']]


class TestSelectExpression:
    def test_arithmetic_in_select(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (10), (20)")
        res = db.execute("SELECT a + 5 FROM t ORDER BY a")
        assert res == [[15], [25]]

    def test_mixed_types_in_select(self, db):
        res = db.execute("SELECT 1, 'hello', 3.14")
        assert len(res[0]) == 3


class TestDistinct:
    def test_distinct_single_col(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (2), (3), (3), (3)")
        res = db.execute("SELECT DISTINCT a FROM t ORDER BY a")
        assert [r[0] for r in res] == [1, 2, 3]

    def test_distinct_multi_col(self, db):
        db.execute("CREATE TABLE t (a INT, b INT)")
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20), (1, 10), (3, 30)")
        res = db.execute("SELECT DISTINCT a, b FROM t ORDER BY a")
        assert res == [[1, 10], [2, 20], [3, 30]]

    def test_distinct_no_dupes(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        res = db.execute("SELECT DISTINCT a FROM t ORDER BY a")
        assert len(res) == 3


class TestLimit:
    def test_limit_basic(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3), (4), (5)")
        res = db.execute("SELECT a FROM t LIMIT 3")
        assert len(res) == 3
        assert [r[0] for r in res] == [1, 2, 3]

    def test_limit_all(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2)")
        res = db.execute("SELECT a FROM t LIMIT 10")
        assert len(res) == 2

    def test_limit_zero(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2)")
        res = db.execute("SELECT a FROM t LIMIT 0")
        assert len(res) == 0

    def test_offset_basic(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3), (4), (5)")
        res = db.execute("SELECT a FROM t ORDER BY a LIMIT 2 OFFSET 2")
        assert [r[0] for r in res] == [3, 4]

    def test_offset_exhaust(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2)")
        res = db.execute("SELECT a FROM t ORDER BY a LIMIT 10 OFFSET 5")
        assert len(res) == 0

    def test_limit_with_where(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3), (4), (5)")
        res = db.execute("SELECT a FROM t WHERE a > 2 ORDER BY a LIMIT 2")
        assert [r[0] for r in res] == [3, 4]

    def test_offset_with_where(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3), (4), (5)")
        res = db.execute("SELECT a FROM t WHERE a > 2 ORDER BY a LIMIT 10 OFFSET 1")
        assert [r[0] for r in res] == [4, 5]

    def test_limit_no_table(self, db):
        res = db.execute("SELECT 1, 2, 3 LIMIT 1")
        assert res == [[1, 2, 3]]
