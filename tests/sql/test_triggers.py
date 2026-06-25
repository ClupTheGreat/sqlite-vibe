import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestCreateTrigger:
    def test_create_trigger_basic(self, db):
        db.execute("CREATE TABLE t (a INT)")
        res = db.execute("CREATE TRIGGER tr AFTER INSERT ON t BEGIN SELECT 1; END")
        assert res == []

    def test_drop_trigger(self, db):
        db.execute("CREATE TABLE t (a INT)")
        db.execute("CREATE TRIGGER tr AFTER INSERT ON t BEGIN SELECT 1; END")
        res = db.execute("DROP TRIGGER tr")
        assert res == []
