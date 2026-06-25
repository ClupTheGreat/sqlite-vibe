import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestCrossJoin:
    def test_cross_join_comma(self, db):
        db.execute('CREATE TABLE t1 (a INT)')
        db.execute('CREATE TABLE t2 (b INT)')
        db.execute('INSERT INTO t1 VALUES (1), (2)')
        db.execute('INSERT INTO t2 VALUES (10), (20)')
        res = db.execute('SELECT * FROM t1, t2 ORDER BY a, b')
        assert res == [[1, 10], [1, 20], [2, 10], [2, 20]]

    def test_cross_join_explicit(self, db):
        db.execute('CREATE TABLE t1 (a INT)')
        db.execute('CREATE TABLE t2 (b INT)')
        db.execute('INSERT INTO t1 VALUES (1), (2)')
        db.execute('INSERT INTO t2 VALUES (10), (20)')
        res = db.execute('SELECT * FROM t1 CROSS JOIN t2 ORDER BY a, b')
        assert res == [[1, 10], [1, 20], [2, 10], [2, 20]]

    def test_cross_join_single_row(self, db):
        db.execute('CREATE TABLE t1 (a INT)')
        db.execute('CREATE TABLE t2 (b INT)')
        db.execute('INSERT INTO t1 VALUES (1)')
        db.execute('INSERT INTO t2 VALUES (10)')
        res = db.execute('SELECT * FROM t1, t2')
        assert res == [[1, 10]]


class TestInnerJoin:
    def test_inner_join_on(self, db):
        db.execute('CREATE TABLE t1 (id INT, val TEXT)')
        db.execute('CREATE TABLE t2 (id INT, description TEXT)')
        db.execute("INSERT INTO t1 VALUES (1, 'a'), (2, 'b'), (3, 'c')")
        db.execute("INSERT INTO t2 VALUES (1, 'x'), (2, 'y'), (4, 'z')")
        res = db.execute('SELECT t1.val, t2.description FROM t1 INNER JOIN t2 ON t1.id = t2.id ORDER BY t1.id')
        assert res == [['a', 'x'], ['b', 'y']]

    def test_inner_join_no_match(self, db):
        db.execute('CREATE TABLE t1 (id INT)')
        db.execute('CREATE TABLE t2 (id INT)')
        db.execute('INSERT INTO t1 VALUES (1)')
        db.execute('INSERT INTO t2 VALUES (2)')
        res = db.execute('SELECT * FROM t1 INNER JOIN t2 ON t1.id = t2.id')
        assert res == []


class TestLeftJoin:
    def test_left_join_basic(self, db):
        db.execute('CREATE TABLE t1 (id INT, val TEXT)')
        db.execute('CREATE TABLE t2 (id INT, description TEXT)')
        db.execute("INSERT INTO t1 VALUES (1, 'a'), (2, 'b'), (3, 'c')")
        db.execute("INSERT INTO t2 VALUES (1, 'x'), (3, 'z')")
        res = db.execute('SELECT t1.val, t2.description FROM t1 LEFT JOIN t2 ON t1.id = t2.id')
        assert res == [['a', 'x'], ['b', None], ['c', 'z']]

    def test_left_join_all_match(self, db):
        db.execute('CREATE TABLE t1 (id INT, val TEXT)')
        db.execute('CREATE TABLE t2 (id INT, description TEXT)')
        db.execute("INSERT INTO t1 VALUES (1, 'a'), (2, 'b')")
        db.execute("INSERT INTO t2 VALUES (1, 'x'), (2, 'y')")
        res = db.execute('SELECT val, description FROM t1 LEFT JOIN t2 ON t1.id = t2.id ORDER BY id')
        assert res == [['a', 'x'], ['b', 'y']]


class TestJoinOrderBy:
    def test_join_order_by(self, db):
        db.execute('CREATE TABLE t1 (id INT, val TEXT)')
        db.execute('CREATE TABLE t2 (id INT)')
        db.execute("INSERT INTO t1 VALUES (1, 'a'), (2, 'b')")
        db.execute("INSERT INTO t2 VALUES (2), (1)")
        res = db.execute("SELECT t1.val, t2.id FROM t1 INNER JOIN t2 ON t1.id = t2.id ORDER BY t2.id")
        assert res == [['a', 1], ['b', 2]]
