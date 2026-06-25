import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestGroupBy:
    def test_group_by_multiple_columns(self, db):
        db.execute("CREATE TABLE t (a INT, b INT, val INT)")
        db.execute("INSERT INTO t VALUES (1, 10, 100), (1, 10, 200), (1, 20, 300), (2, 10, 400)")
        res = db.execute("SELECT a, b, SUM(val) FROM t GROUP BY a, b ORDER BY a, b")
        assert res == [[1, 10, 300], [1, 20, 300], [2, 10, 400]]

    def test_group_by_with_order_by(self, db):
        db.execute("CREATE TABLE t (cat TEXT, val INT)")
        db.execute("INSERT INTO t VALUES ('b', 30), ('a', 10), ('a', 20), ('b', 5)")
        res = db.execute("SELECT cat, SUM(val) AS total FROM t GROUP BY cat ORDER BY total")
        assert res == [['b', 35], ['a', 30]]

    def test_group_by_having_count(self, db):
        db.execute("CREATE TABLE t (cat TEXT, val INT)")
        db.execute("INSERT INTO t VALUES ('a', 5), ('a', 10), ('b', 20), ('b', 30), ('c', 100)")
        res = db.execute("SELECT cat, COUNT(*) FROM t GROUP BY cat HAVING COUNT(*) > 1 ORDER BY cat")
        assert res == [['a', 2], ['b', 2]]


class TestCountDistinct:
    def test_count_distinct(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (1), (2), (3), (3), (3)")
        res = db.execute("SELECT COUNT(DISTINCT a) FROM t")
        assert res == [[3]]

    def test_count_distinct_with_null(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (NULL), (1), (NULL), (2)")
        res = db.execute("SELECT COUNT(DISTINCT a) FROM t")
        assert res == [[2]]


class TestAggregateExpressions:
    def test_avg_rounding(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2)")
        res = db.execute("SELECT AVG(a) FROM t")
        assert abs(res[0][0] - 1.5) < 0.001

    def test_total_vs_sum(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2)")
        res = db.execute("SELECT TOTAL(a) FROM t")
        assert abs(res[0][0] - 3.0) < 0.001

    def test_min_strings(self, db):
        db.execute("CREATE TABLE t (a TEXT)")
        db.execute("INSERT INTO t VALUES ('banana'), ('apple'), ('cherry')")
        res = db.execute("SELECT MIN(a) FROM t")
        assert res == [['apple']]

    def test_max_strings(self, db):
        db.execute("CREATE TABLE t (a TEXT)")
        db.execute("INSERT INTO t VALUES ('banana'), ('apple'), ('cherry')")
        res = db.execute("SELECT MAX(a) FROM t")
        assert res == [['cherry']]

    def test_group_concat_separator(self, db):
        db.execute("CREATE TABLE t (a TEXT)")
        db.execute("INSERT INTO t VALUES ('x'), ('y'), ('z')")
        res = db.execute("SELECT GROUP_CONCAT(a, ';') FROM t")
        assert res == [['x;y;z']]


class TestAggregateWithWhere:
    def test_sum_where(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3), (4), (5)")
        res = db.execute("SELECT SUM(a) FROM t WHERE a > 2")
        assert res == [[12]]
