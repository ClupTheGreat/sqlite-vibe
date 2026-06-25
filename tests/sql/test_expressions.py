import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestCase:
    def test_case_searched(self, db):
        res = db.execute("SELECT CASE WHEN 1 > 0 THEN 'yes' ELSE 'no' END")
        assert res == [['yes']]

    def test_case_searched_false(self, db):
        res = db.execute("SELECT CASE WHEN 1 < 0 THEN 'yes' ELSE 'no' END")
        assert res == [['no']]

    def test_case_searched_no_else(self, db):
        res = db.execute("SELECT CASE WHEN 1 > 2 THEN 'yes' END")
        assert res == [[None]]

    def test_case_in_where(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'x'), (2, 'y'), (3, 'z')")
        res = db.execute("SELECT b FROM t WHERE CASE WHEN a > 1 THEN 1 ELSE 0 END ORDER BY a")
        assert res == [['y'], ['z']]


class TestInList:
    def test_in_list(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3), (4), (5)")
        res = db.execute("SELECT a FROM t WHERE a IN (2, 4) ORDER BY a")
        assert res == [[2], [4]]

    def test_not_in_list(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        res = db.execute("SELECT a FROM t WHERE a NOT IN (2) ORDER BY a")
        assert res == [[1], [3]]

    def test_in_list_strings(self, db):
        db.execute("CREATE TABLE t (a TEXT)")
        db.execute("INSERT INTO t VALUES ('x'), ('y'), ('z')")
        res = db.execute("SELECT a FROM t WHERE a IN ('x', 'z') ORDER BY a")
        assert res == [['x'], ['z']]

    def test_not_in_empty_list(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1)")
        res = db.execute("SELECT a FROM t WHERE a NOT IN ()")
        assert res == [[1]]


class TestLike:
    def test_like_percent(self, db):
        res = db.execute("SELECT 'hello' LIKE 'h%'")
        assert res == [[1]]

    def test_like_underscore(self, db):
        res = db.execute("SELECT 'hello' LIKE 'h____'")
        assert res == [[1]]

    def test_like_no_match(self, db):
        res = db.execute("SELECT 'hello' LIKE 'world'")
        assert res == [[0]]

    def test_like_in_where(self, db):
        db.execute("CREATE TABLE t (a TEXT)")
        db.execute("INSERT INTO t VALUES ('apple'), ('banana'), ('cherry')")
        res = db.execute("SELECT a FROM t WHERE a LIKE 'b%' ORDER BY a")
        assert res == [['banana']]

    def test_not_like_match(self, db):
        res = db.execute("SELECT 'hello' NOT LIKE 'h%'")
        assert res == [[0]]

    def test_not_like_no_match(self, db):
        res = db.execute("SELECT 'hello' NOT LIKE 'x%'")
        assert res == [[1]]


class TestBetween:
    def test_between_literal_true(self, db):
        res = db.execute("SELECT 5 BETWEEN 1 AND 10")
        assert res == [[1]]

    def test_between_literal_false(self, db):
        res = db.execute("SELECT 0 BETWEEN 1 AND 10")
        assert res == [[0]]

    def test_between_equal_bounds(self, db):
        res = db.execute("SELECT 5 BETWEEN 5 AND 5")
        assert res == [[1]]

    def test_between_in_where(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3), (4), (5)")
        res = db.execute("SELECT a FROM t WHERE a BETWEEN 2 AND 4 ORDER BY a")
        assert res == [[2], [3], [4]]

    def test_not_between(self, db):
        res = db.execute("SELECT 5 NOT BETWEEN 1 AND 3")
        assert res == [[1]]

    def test_not_between_false(self, db):
        res = db.execute("SELECT 2 NOT BETWEEN 1 AND 3")
        assert res == [[0]]

    def test_not_between_in_where(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3), (4), (5)")
        res = db.execute("SELECT a FROM t WHERE a NOT BETWEEN 2 AND 4 ORDER BY a")
        assert res == [[1], [5]]


class TestStringOperators:
    def test_concatenate(self, db):
        res = db.execute("SELECT 'Hello' || ' ' || 'World'")
        assert res == [['Hello World']]


class TestNullOperators:
    def test_is_null(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (NULL), (1)")
        res = db.execute("SELECT a FROM t WHERE a IS NULL")
        assert res == [[None]]

    def test_is_not_null(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (NULL), (1)")
        res = db.execute("SELECT a FROM t WHERE a IS NOT NULL")
        assert res == [[1]]
