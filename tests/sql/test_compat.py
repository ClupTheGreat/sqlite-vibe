"""Compatibility tests: run same SQL against real sqlite3 and pysqlite."""
import pytest
import sqlite3
from pysqlite import Database as PyDatabase

SQL_SAMPLES = [
    # DDL + DML
    "CREATE TABLE t (a INT, b TEXT); INSERT INTO t VALUES (1, 'hello'); SELECT * FROM t",
    # WHERE
    "CREATE TABLE t (a INT); INSERT INTO t VALUES (1), (2), (3); SELECT * FROM t WHERE a > 1",
    # ORDER BY
    "CREATE TABLE t (a INT); INSERT INTO t VALUES (3), (1), (2); SELECT * FROM t ORDER BY a",
    # String functions
    "SELECT LENGTH('hello'), UPPER('hello'), LOWER('HELLO')",
    # Math
    "SELECT ABS(-5), LENGTH('abc')",
    # Aggregates
    "CREATE TABLE t (a INT); INSERT INTO t VALUES (1), (2), (3); SELECT COUNT(*), SUM(a), AVG(a) FROM t",
    # GROUP BY
    "CREATE TABLE t (a INT, b INT); INSERT INTO t VALUES (1, 10), (1, 20), (2, 30); SELECT a, SUM(b) FROM t GROUP BY a ORDER BY a",
    # INSERT OR IGNORE
    "CREATE TABLE t (a INT PRIMARY KEY, b TEXT); INSERT INTO t VALUES (1, 'a'); INSERT OR IGNORE INTO t VALUES (1, 'b'); SELECT * FROM t",
    # RETURNING
    "CREATE TABLE t (a INT PRIMARY KEY, b TEXT); INSERT INTO t VALUES (1, 'hello') RETURNING *",
    # Subquery
    "CREATE TABLE t (a INT); INSERT INTO t VALUES (1), (2); SELECT * FROM (SELECT * FROM t) AS sub WHERE a > 1",
]


@pytest.mark.parametrize('sql', SQL_SAMPLES, ids=lambda s: s[:40])
def test_compat(sql):
    """Run SQL against both sqlite3 and pysqlite; compare results."""
    # sqlite3
    conn = sqlite3.connect(':memory:')
    try:
        for stmt in sql.split(';'):
            stmt = stmt.strip()
            if stmt:
                cur = conn.execute(stmt)
        sqlite_result = [list(row) for row in cur.fetchall()]
    finally:
        conn.close()

    # pysqlite
    pydb = PyDatabase(':memory:')
    try:
        result = None
        for stmt in sql.split(';'):
            stmt = stmt.strip()
            if stmt:
                result = pydb.execute(stmt)
        py_result = [list(row) for row in result] if result else []
    finally:
        pydb.close()

    assert py_result == sqlite_result, f'\nSQL: {sql}\nsqlite3: {sqlite_result}\npysqlite: {py_result}'


def test_compat_parameter_binding():
    """Test parameter binding compatibility."""
    # sqlite3
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE t (a INT, b TEXT)')
    conn.execute('INSERT INTO t VALUES (?, ?)', (1, 'hello'))
    conn.execute('INSERT INTO t VALUES (:a, :b)', {'a': 2, 'b': 'world'})
    sqlite_result = [list(row) for row in conn.execute('SELECT * FROM t ORDER BY a').fetchall()]
    conn.close()

    # pysqlite
    pydb = PyDatabase(':memory:')
    pydb.execute('CREATE TABLE t (a INT, b TEXT)')
    pydb.execute_params('INSERT INTO t VALUES (?, ?)', {'1': 1, '2': 'hello'})
    pydb.execute_params('INSERT INTO t VALUES (:a, :b)', {'a': 2, 'b': 'world'})
    py_result = [list(row) for row in pydb.execute('SELECT * FROM t ORDER BY a')]
    pydb.close()

    assert py_result == sqlite_result
