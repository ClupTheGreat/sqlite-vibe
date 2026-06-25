import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestRowNumber:
    def test_row_number(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (3), (1), (2)")
        res = db.execute("SELECT a, ROW_NUMBER() OVER (ORDER BY a) AS rn FROM t ORDER BY a")
        assert res == [[1, 1], [2, 2], [3, 3]]

    def test_row_number_no_order(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (10), (20)")
        res = db.execute("SELECT ROW_NUMBER() OVER () AS rn FROM t ORDER BY a")
        assert len(res) == 2
        assert res[0][0] == 1
        assert res[1][0] == 2


class TestRank:
    def test_rank_basic(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (2), (3)")
        res = db.execute("SELECT a, RANK() OVER (ORDER BY a) AS r FROM t ORDER BY a")
        assert res == [[1, 1], [2, 2], [2, 2], [3, 4]]


class TestDenseRank:
    def test_dense_rank_basic(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (2), (3)")
        res = db.execute("SELECT a, DENSE_RANK() OVER (ORDER BY a) AS dr FROM t ORDER BY a")
        assert res == [[1, 1], [2, 2], [2, 2], [3, 3]]


class TestAggregateOverWindow:
    def test_sum_over_window(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        res = db.execute("SELECT a, SUM(a) OVER (ORDER BY a) AS running FROM t ORDER BY a")
        assert res == [[1, 1], [2, 3], [3, 6]]

    def test_min_over_window(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (3), (1), (2)")
        res = db.execute("SELECT a, MIN(a) OVER (ORDER BY a) AS mn FROM t ORDER BY a")
        assert res == [[1, 1], [2, 1], [3, 1]]

    def test_max_over_window(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (3), (2)")
        res = db.execute("SELECT a, MAX(a) OVER (ORDER BY a) AS mx FROM t ORDER BY a")
        assert res == [[1, 1], [2, 2], [3, 3]]


class TestPartitionBy:
    def test_row_number_partition(self, db):
        db.execute("CREATE TABLE t (grp TEXT, val INT)")
        db.execute("INSERT INTO t VALUES ('a', 10), ('a', 20), ('b', 30), ('b', 40)")
        res = db.execute("SELECT grp, val, ROW_NUMBER() OVER (PARTITION BY grp ORDER BY val) AS rn FROM t ORDER BY grp, val")
        assert res == [['a', 10, 1], ['a', 20, 2], ['b', 30, 1], ['b', 40, 2]]

    def test_sum_partition(self, db):
        db.execute("CREATE TABLE t (grp TEXT, val INT)")
        db.execute("INSERT INTO t VALUES ('a', 10), ('a', 20), ('b', 30)")
        res = db.execute("SELECT grp, val, SUM(val) OVER (PARTITION BY grp) AS total FROM t ORDER BY grp, val")
        assert res == [['a', 10, 30], ['a', 20, 30], ['b', 30, 30]]


class TestMultipleWindows:
    def test_multiple_window_functions(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        res = db.execute("SELECT a, ROW_NUMBER() OVER (ORDER BY a) AS rn, SUM(a) OVER (ORDER BY a) AS sm FROM t ORDER BY a")
        assert res == [[1, 1, 1], [2, 2, 3], [3, 3, 6]]


class TestNamedWindow:
    def test_named_window(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        res = db.execute("SELECT a, ROW_NUMBER() OVER w AS rn FROM t WINDOW w AS (ORDER BY a) ORDER BY a")
        assert res == [[1, 1], [2, 2], [3, 3]]

    def test_named_window_multiple_refs(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        res = db.execute("SELECT a, ROW_NUMBER() OVER w AS rn, SUM(a) OVER w AS sm FROM t WINDOW w AS (ORDER BY a) ORDER BY a")
        assert res == [[1, 1, 1], [2, 2, 3], [3, 3, 6]]


class TestWindowDesc:
    def test_window_order_desc(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        res = db.execute("SELECT a, ROW_NUMBER() OVER (ORDER BY a DESC) AS rn FROM t ORDER BY a")
        assert res == [[1, 3], [2, 2], [3, 1]]
