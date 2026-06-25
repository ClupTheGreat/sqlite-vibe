import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestJsonScalar:
    def test_json_valid_valid(self, db):
        res = db.execute("SELECT JSON_VALID('{\"a\":1}')")
        assert res == [[1]]

    def test_json_valid_invalid(self, db):
        res = db.execute("SELECT JSON_VALID('not json')")
        assert res == [[0]]

    def test_json_type(self, db):
        res = db.execute("SELECT JSON_TYPE('{\"a\":1}', '$.a')")
        assert res == [['integer']]

    def test_json_type_object(self, db):
        res = db.execute("SELECT JSON_TYPE('{\"a\":1}')")
        assert res == [['object']]

    def test_json_array_length(self, db):
        res = db.execute("SELECT JSON_ARRAY_LENGTH('[1,2,3]')")
        assert res == [[3]]

    def test_json_extract(self, db):
        res = db.execute("SELECT JSON_EXTRACT('{\"a\":10}', '$.a')")
        assert res == [[10]]

    def test_json_extract_nested(self, db):
        res = db.execute("SELECT JSON_EXTRACT('{\"a\":{\"b\":42}}', '$.a.b')")
        assert res == [[42]]

    def test_json_array(self, db):
        res = db.execute("SELECT JSON_ARRAY(1, 2, 3)")
        assert res == [['[1,2,3]']]

    def test_json_object(self, db):
        res = db.execute("SELECT JSON_OBJECT('a', 1, 'b', 2)")
        assert res == [['{"a":1,"b":2}']]

    def test_json_set(self, db):
        res = db.execute("SELECT JSON_SET('{\"a\":1}', '$.a', 99)")
        assert res == [['{"a":99}']]

    def test_json_set_add_key(self, db):
        res = db.execute("SELECT JSON_SET('{\"a\":1}', '$.b', 2)")
        assert res == [['{"a":1,"b":2}']]

    def test_json_insert(self, db):
        res = db.execute("SELECT JSON_INSERT('{\"a\":1}', '$.a', 99)")
        assert res == [['{"a":1}']]  # doesn't overwrite

    def test_json_replace(self, db):
        res = db.execute("SELECT JSON_REPLACE('{\"a\":1}', '$.a', 99)")
        assert res == [['{"a":99}']]

    def test_json_remove(self, db):
        res = db.execute("SELECT JSON_REMOVE('{\"a\":1,\"b\":2}', '$.a')")
        assert res == [['{"b":2}']]


class TestJsonAggregate:
    def test_json_group_array(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("INSERT INTO t VALUES (1), (2), (3)")
        res = db.execute("SELECT JSON_GROUP_ARRAY(a) FROM t")
        assert res == [['[1,2,3]']]

    def test_json_group_object(self, db):
        db.execute("CREATE TABLE t (k TEXT, v INT)")
        db.execute("INSERT INTO t VALUES ('a', 1), ('b', 2)")
        res = db.execute("SELECT JSON_GROUP_OBJECT(k, v) FROM t")
        assert res == [['{"a":1,"b":2}']]
