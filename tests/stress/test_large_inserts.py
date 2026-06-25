"""Stress test: large number of inserts."""

import pytest
from pysqlite import Database


def test_large_insert(db):
    db.execute("CREATE TABLE t (id INT PRIMARY KEY, val TEXT)")
    for i in range(50):
        db.execute(f"INSERT INTO t VALUES ({i}, 'value_{i}')")
    res = db.execute("SELECT COUNT(*) FROM t")
    assert res[0][0] == 50


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()
