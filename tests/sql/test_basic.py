"""End-to-end SQL integration tests."""

import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestDDL:
    def test_create_table(self, db):
        res = db.execute('CREATE TABLE t (a INT, b TEXT)')
        assert res == []

    def test_create_and_select(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        res = db.execute('SELECT * FROM t')
        assert res == []

    def test_create_if_not_exists(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('CREATE TABLE IF NOT EXISTS t (a INT)')


class TestDML:
    def test_insert_and_select(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        res = db.execute('SELECT * FROM t')
        assert res == [[1, 'hello']]

    def test_insert_multiple(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (10)')
        db.execute('INSERT INTO t VALUES (20)')
        db.execute('INSERT INTO t VALUES (30)')
        res = db.execute('SELECT * FROM t ORDER BY a')
        assert res == [[10], [20], [30]]

    def test_insert_select(self, db):
        db.execute('CREATE TABLE t1 (a INT)')
        db.execute('CREATE TABLE t2 (a INT)')
        db.execute('INSERT INTO t1 VALUES (1), (2), (3)')
        db.execute('INSERT INTO t2 SELECT * FROM t1')
        res = db.execute('SELECT * FROM t2 ORDER BY a')
        assert res == [[1], [2], [3]]

    def test_update(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'x'), (2, 'y')")
        db.execute("UPDATE t SET b = 'z' WHERE a = 1")
        res = db.execute('SELECT b FROM t ORDER BY a')
        assert res == [['z'], ['y']]

    def test_delete(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3)')
        db.execute('DELETE FROM t WHERE a = 2')
        res = db.execute('SELECT a FROM t ORDER BY a')
        assert res == [[1], [3]]


class TestSelect:
    def test_select_literal(self, db):
        res = db.execute('SELECT 1')
        assert res == [[1]]

    def test_select_literals(self, db):
        res = db.execute('SELECT 1, 2, 3')
        assert res == [[1, 2, 3]]

    def test_select_string(self, db):
        res = db.execute("SELECT 'hello'")
        assert res == [['hello']]

    def test_select_expression(self, db):
        res = db.execute('SELECT 1 + 2')
        assert res == [[3]]

    def test_select_mul(self, db):
        res = db.execute('SELECT 3 * 4')
        assert res == [[12]]

    def test_select_multiple_rows(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (10), (20), (30)')
        res = db.execute('SELECT * FROM t')
        assert len(res) == 3


class TestExpressions:
    def test_where(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3), (4)')
        res = db.execute('SELECT a FROM t WHERE a > 2')
        assert res == [[3], [4]]

    def test_and(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute('INSERT INTO t VALUES (1, 10), (2, 20), (3, 30)')
        res = db.execute('SELECT a FROM t WHERE a > 1 AND b < 30')
        assert res == [[2]]

    def test_or(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3)')
        res = db.execute('SELECT a FROM t WHERE a = 1 OR a = 3')
        assert len(res) == 2

    def test_is_null(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (NULL), (1)')
        res = db.execute('SELECT a FROM t WHERE a IS NULL')
        assert res == [[None]]

    def test_is_not_null(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (NULL), (1)')
        res = db.execute('SELECT a FROM t WHERE a IS NOT NULL')
        assert res == [[1]]


class TestOrderBy:
    def test_order_by_asc(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (3), (1), (2)')
        res = db.execute('SELECT a FROM t ORDER BY a')
        assert res == [[1], [2], [3]]

    def test_order_by_desc(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3)')
        res = db.execute('SELECT a FROM t ORDER BY a DESC')
        assert res == [[3], [2], [1]]


class TestFunctions:
    def test_length(self, db):
        res = db.execute("SELECT LENGTH('hello')")
        assert res == [[5]]

    def test_abs(self, db):
        res = db.execute('SELECT ABS(-5)')
        assert res == [[5]]

    def test_upper(self, db):
        res = db.execute("SELECT UPPER('hello')")
        assert res == [['HELLO']]

    def test_lower(self, db):
        res = db.execute("SELECT LOWER('HELLO')")
        assert res == [['hello']]


class TestAggregates:
    def test_count_star(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3)')
        res = db.execute('SELECT COUNT(*) FROM t')
        assert res == [[3]]

    def test_count_col(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (NULL), (3)')
        res = db.execute('SELECT COUNT(a) FROM t')
        assert res == [[2]]

    def test_sum(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3)')
        res = db.execute('SELECT SUM(a) FROM t')
        assert res == [[6]]

    def test_avg(self, db):
        db.execute('CREATE TABLE t (a REAL)')
        db.execute('INSERT INTO t VALUES (1.0), (2.0), (3.0)')
        res = db.execute('SELECT AVG(a) FROM t')
        assert abs(res[0][0] - 2.0) < 0.001

    def test_min(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (3), (1), (2)')
        res = db.execute('SELECT MIN(a) FROM t')
        assert res == [[1]]

    def test_max(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (3), (1), (2)')
        res = db.execute('SELECT MAX(a) FROM t')
        assert res == [[3]]

    def test_group_concat(self, db):
        db.execute('CREATE TABLE t (a TEXT)')
        db.execute("INSERT INTO t VALUES ('x'), ('y'), ('z')")
        res = db.execute('SELECT GROUP_CONCAT(a) FROM t')
        assert res == [['x,y,z']]

    def test_group_by(self, db):
        db.execute('CREATE TABLE t (cat TEXT, val INT)')
        db.execute("INSERT INTO t VALUES ('a', 10), ('a', 20), ('b', 30)")
        res = db.execute('SELECT cat, SUM(val) FROM t GROUP BY cat ORDER BY cat')
        assert res == [['a', 30], ['b', 30]]

    def test_group_by_count(self, db):
        db.execute('CREATE TABLE t (cat TEXT)')
        db.execute("INSERT INTO t VALUES ('a'), ('a'), ('b')")
        res = db.execute('SELECT cat, COUNT(*) FROM t GROUP BY cat ORDER BY cat')
        assert res == [['a', 2], ['b', 1]]

    def test_group_by_having(self, db):
        db.execute('CREATE TABLE t (cat TEXT, val INT)')
        db.execute("INSERT INTO t VALUES ('a', 1), ('a', 2), ('b', 10)")
        res = db.execute('SELECT cat, SUM(val) FROM t GROUP BY cat HAVING SUM(val) > 5')
        assert res == [['b', 10]]

    def test_multiple_aggregates(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3)')
        res = db.execute('SELECT COUNT(*), SUM(a), AVG(a), MIN(a), MAX(a) FROM t')
        row = res[0]
        assert row[0] == 3  # COUNT
        assert row[1] == 6  # SUM
        assert row[2] == 2.0  # AVG
        assert row[3] == 1  # MIN
        assert row[4] == 3  # MAX

    def test_where_with_aggregate(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1), (2), (3), (4)')
        res = db.execute('SELECT COUNT(*) FROM t WHERE a > 2')
        assert res == [[2]]


class TestMathFunctions:
    def test_abs(self, db):
        res = db.execute('SELECT ABS(-5)')
        assert res == [[5]]

    def test_sin(self, db):
        res = db.execute('SELECT SIN(0)')
        import math
        assert abs(res[0][0] - 0.0) < 0.001

    def test_cos(self, db):
        res = db.execute('SELECT COS(0)')
        assert abs(res[0][0] - 1.0) < 0.001

    def test_ceil(self, db):
        res = db.execute('SELECT CEIL(1.5)')
        assert res == [[2]]

    def test_floor(self, db):
        res = db.execute('SELECT FLOOR(1.5)')
        assert res == [[1]]

    def test_round(self, db):
        res = db.execute('SELECT ROUND(1.5)')
        assert res == [[2]]

    def test_log(self, db):
        res = db.execute('SELECT LOG(10)')
        import math
        assert abs(res[0][0] - 2.302585) < 0.001

    def test_log10(self, db):
        res = db.execute('SELECT LOG10(100)')
        assert abs(res[0][0] - 2.0) < 0.001

    def test_sqrt(self, db):
        res = db.execute('SELECT SQRT(16)')
        assert abs(res[0][0] - 4.0) < 0.001

    def test_exp(self, db):
        res = db.execute('SELECT EXP(1)')
        import math
        assert abs(res[0][0] - math.e) < 0.001

    def test_sin_negative(self, db):
        res = db.execute('SELECT SIN(-1)')
        import math
        assert abs(res[0][0] - math.sin(-1)) < 0.001

    def test_cos_negative(self, db):
        res = db.execute('SELECT COS(-1)')
        import math
        assert abs(res[0][0] - math.cos(-1)) < 0.001

    def test_sqrt_zero(self, db):
        res = db.execute('SELECT SQRT(0)')
        assert abs(res[0][0]) < 0.001

    def test_exp_zero(self, db):
        res = db.execute('SELECT EXP(0)')
        assert abs(res[0][0] - 1.0) < 0.001


class TestDateTimeFunctions:
    def test_date_now(self, db):
        from datetime import datetime, timezone
        res = db.execute("SELECT DATE('now')")
        expected = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        assert res[0][0] == expected

    def test_time_now(self, db):
        res = db.execute("SELECT TIME('now')")
        assert ':' in res[0][0]

    def test_datetime_now(self, db):
        from datetime import datetime, timezone
        res = db.execute("SELECT DATETIME('now')")
        assert ' ' in res[0][0]

    def test_julianday(self, db):
        res = db.execute("SELECT JULIANDAY('2024-01-01')")
        assert abs(res[0][0] - 2460310.0) < 0.001

    def test_date_format(self, db):
        res = db.execute("SELECT DATE('2024-03-15')")
        assert res[0][0] == '2024-03-15'

    def test_date_add_days(self, db):
        res = db.execute("SELECT DATE('2024-01-01', '+1 day')")
        assert res[0][0] == '2024-01-02'

    def test_date_add_months(self, db):
        res = db.execute("SELECT DATE('2024-01-01', '+1 month')")
        assert res[0][0] == '2024-02-01'

    def test_date_start_of_month(self, db):
        res = db.execute("SELECT DATE('2024-03-15', 'start of month')")
        assert res[0][0] == '2024-03-01'

    def test_date_start_of_year(self, db):
        res = db.execute("SELECT DATE('2024-03-15', 'start of year')")
        assert res[0][0] == '2024-01-01'

    def test_strftime(self, db):
        res = db.execute("SELECT STRFTIME('%Y-%m-%d', '2024-06-15')")
        assert res[0][0] == '2024-06-15'

    def test_strftime_format(self, db):
        res = db.execute("SELECT STRFTIME('%d/%m/%Y', '2024-03-15')")
        assert res[0][0] == '15/03/2024'

    def test_date_localtime(self, db):
        res = db.execute("SELECT DATE('now', 'localtime')")
        assert '-' in res[0][0]

    def test_unixepoch(self, db):
        res = db.execute("SELECT UNIXEPOCH('2024-01-01')")
        assert res[0][0] == 1704067200

    def test_date_sub_days(self, db):
        res = db.execute("SELECT DATE('2024-01-10', '-5 days')")
        assert res[0][0] == '2024-01-05'

    def test_datetime_iso(self, db):
        res = db.execute("SELECT DATETIME('2024-01-01T12:30:00')")
        assert res[0][0] == '2024-01-01 12:30:00'


class TestViews:
    def test_create_view_and_select(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20), (3, 30)")
        db.execute("CREATE VIEW v AS SELECT a, b FROM t")
        res = db.execute("SELECT * FROM v")
        assert len(res) == 3
        assert res[0] == [1, 10]
        assert res[1] == [2, 20]
        assert res[2] == [3, 30]

    def test_create_view_with_filter(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20), (3, 30)")
        db.execute("CREATE VIEW v AS SELECT a, b FROM t WHERE a > 1")
        res = db.execute("SELECT * FROM v")
        assert len(res) == 2
        assert res[0] == [2, 20]
        assert res[1] == [3, 30]

    def test_create_view_column_select(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20)")
        db.execute("CREATE VIEW v AS SELECT a, b FROM t")
        res = db.execute("SELECT a FROM v")
        assert res == [[1], [2]]

    def test_create_view_expression(self, db):
        db.execute('CREATE TABLE t (a INT, b INT)')
        db.execute("INSERT INTO t VALUES (1, 10), (2, 20)")
        db.execute("CREATE VIEW v AS SELECT a * 2 AS double_a FROM t")
        res = db.execute("SELECT double_a FROM v")
        assert res == [[2], [4]]

    def test_drop_view(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute("INSERT INTO t VALUES (1)")
        db.execute("CREATE VIEW v AS SELECT a FROM t")
        res = db.execute("SELECT * FROM v")
        assert res == [[1]]
        assert db.schema.get_view('v') is not None
        db.execute("DROP VIEW v")
        assert db.schema.get_view('v') is None


class TestPragmas:
    def test_page_count(self, db):
        db.execute('CREATE TABLE t (a INT)')
        res = db.execute('PRAGMA page_count')
        assert res[0][0] >= 1

    def test_page_size(self, db):
        res = db.execute('PRAGMA page_size')
        assert res[0][0] == 4096

    def test_table_info(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT NOT NULL)')
        res = db.execute("PRAGMA table_info('t')")
        assert len(res) == 2
        assert res[0] == [0, 'a', 'INT', 0, '', 1]
        assert res[1] == [1, 'b', 'TEXT', 1, '', 0]

    def test_index_list(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('CREATE UNIQUE INDEX idx_t_a ON t(a)')
        res = db.execute("PRAGMA index_list('t')")
        assert len(res) == 1
        assert res[0][1] == 'idx_t_a'
        assert res[0][2] == 1  # unique

    def test_index_info(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute('CREATE INDEX idx_t_a ON t(a)')
        res = db.execute("PRAGMA index_info('idx_t_a')")
        assert len(res) == 1
        assert res[0] == [0, 0, 'a']

    def test_encoding(self, db):
        res = db.execute('PRAGMA encoding')
        assert res[0][0] == 'UTF-8'

    def test_database_list(self, db):
        res = db.execute('PRAGMA database_list')
        assert len(res) == 1
        assert res[0][1] == 'main'

    def test_user_version(self, db):
        res = db.execute('PRAGMA user_version')
        assert res[0][0] == 0

    def test_freelist_count(self, db):
        res = db.execute('PRAGMA freelist_count')
        assert res[0][0] == 0


class TestSubqueryFrom:
    def test_basic_subquery(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1)')
        db.execute('INSERT INTO t VALUES (2)')
        res = db.execute('SELECT * FROM (SELECT a FROM t) AS sub')
        assert res == [[1], [2]]

    def test_subquery_with_where(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1)')
        db.execute('INSERT INTO t VALUES (2)')
        db.execute('INSERT INTO t VALUES (3)')
        res = db.execute('SELECT * FROM (SELECT a FROM t WHERE a > 1) AS sub')
        assert res == [[2], [3]]

    def test_subquery_column_select(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("INSERT INTO t VALUES (2, 'world')")
        res = db.execute('SELECT sub.a FROM (SELECT a, b FROM t) AS sub WHERE sub.a > 1')
        assert res == [[2]]

    def test_subquery_expression_col(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1)')
        db.execute('INSERT INTO t VALUES (2)')
        res = db.execute('SELECT x FROM (SELECT a*2 AS x FROM t) AS sub')
        assert res == [[2], [4]]

    def test_subquery_alias_ref(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (1)')
        db.execute('INSERT INTO t VALUES (2)')
        res = db.execute('SELECT x FROM (SELECT a+10 AS x FROM t) AS sub')
        assert len(res) == 2


class TestReturning:
    def test_insert_returning_col(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        res = db.execute("INSERT INTO t VALUES (2, 'world') RETURNING a")
        assert res == [[2]]

    def test_insert_returning_star(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        res = db.execute("INSERT INTO t VALUES (1, 'hello') RETURNING *")
        assert res == [[1, 'hello']]

    def test_insert_returning_multi(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        res = db.execute("INSERT INTO t VALUES (1, 'a'), (2, 'b') RETURNING a, b")
        assert res == [[1, 'a'], [2, 'b']]

    def test_update_returning_star(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("INSERT INTO t VALUES (2, 'world')")
        res = db.execute("UPDATE t SET b = 'bar' WHERE a = 2 RETURNING *")
        assert res == [[2, 'bar']]

    def test_delete_returning_col(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('INSERT INTO t VALUES (10)')
        db.execute('INSERT INTO t VALUES (20)')
        res = db.execute('DELETE FROM t WHERE a = 10 RETURNING a')
        assert res == [[10]]


class TestUpsert:
    def test_on_conflict_nothing(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("INSERT INTO t VALUES (2, 'world')")
        res = db.execute("INSERT INTO t VALUES (1, 'dup') ON CONFLICT DO NOTHING")
        res = db.execute('SELECT * FROM t')
        assert res == [[1, 'hello'], [2, 'world']]

    def test_on_conflict_nothing_new_row(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("INSERT INTO t VALUES (3, 'new') ON CONFLICT DO NOTHING")
        res = db.execute('SELECT * FROM t')
        assert res == [[1, 'hello'], [3, 'new']]

    def test_insert_or_ignore(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("INSERT OR IGNORE INTO t VALUES (1, 'ignored')")
        res = db.execute('SELECT * FROM t')
        assert res == [[1, 'hello']]

    def test_upsert_integer_pk_no_pk_value(self, db):
        """ON CONFLICT with auto-generated rowid (no explicit PK in values)."""
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("INSERT INTO t VALUES (2, 'world')")
        db.execute("INSERT INTO t VALUES (3, 'new') ON CONFLICT DO NOTHING")
        res = db.execute('SELECT * FROM t ORDER BY a')
        assert res == [[1, 'hello'], [2, 'world'], [3, 'new']]


    def test_on_conflict_do_update_excluded(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("INSERT INTO t VALUES (1, 'world') ON CONFLICT DO UPDATE SET b = excluded.b")
        res = db.execute('SELECT * FROM t ORDER BY a')
        assert res == [[1, 'world']]

    def test_on_conflict_do_update_literal(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("INSERT INTO t VALUES (1, 'ignored') ON CONFLICT DO UPDATE SET b = 'bar'")
        res = db.execute('SELECT * FROM t ORDER BY a')
        assert res == [[1, 'bar']]

    def test_on_conflict_do_update_no_conflict(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT)')
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        db.execute("INSERT INTO t VALUES (2, 'new') ON CONFLICT DO UPDATE SET b = excluded.b")
        res = db.execute('SELECT * FROM t ORDER BY a')
        assert res == [[1, 'hello'], [2, 'new']]


class TestStrict:
    def test_strict_valid_insert(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT) STRICT")
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        res = db.execute('SELECT * FROM t')
        assert res == [[1, 'hello']]

    def test_strict_rejects_wrong_type(self, db):
        db.execute("CREATE TABLE t (a INT, b TEXT) STRICT")
        import pytest
        with pytest.raises(Exception, match='STRICT table'):
            db.execute("INSERT INTO t VALUES ('not_int', 'hello')")


class TestParameterBinding:
    def test_named_param(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute_params("INSERT INTO t VALUES (:a, :b)", {"a": 1, "b": "hello"})
        res = db.execute_params("SELECT * FROM t WHERE a = :a", {"a": 1})
        assert res == [[1, 'hello']]

    def test_positional_param(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute_params("INSERT INTO t VALUES (?1, ?2)", {"1": 1, "2": "hello"})
        res = db.execute_params("SELECT * FROM t WHERE a = ?", {"1": 1})
        assert res == [[1, 'hello']]

    def test_auto_indexed_param(self, db):
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute_params("INSERT INTO t VALUES (?, ?)", {"1": 1, "2": "hello"})
        res = db.execute_params("SELECT * FROM t WHERE a = ? AND b = ?", {"1": 1, "2": "hello"})
        assert res == [[1, 'hello']]

    def test_at_param(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute_params("INSERT INTO t VALUES (@a)", {"a": 42})
        res = db.execute_params("SELECT * FROM t WHERE a = @a", {"a": 42})
        assert res == [[42]]

    def test_dollar_param(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute_params("INSERT INTO t VALUES ($a)", {"a": 99})
        res = db.execute_params("SELECT * FROM t WHERE a = $a", {"a": 99})
        assert res == [[99]]


class TestTransactions:
    def test_begin_commit(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('BEGIN')
        db.execute('INSERT INTO t VALUES (1)')
        db.execute('COMMIT')
        res = db.execute('SELECT * FROM t')
        assert res == [[1]]

    def test_begin_rollback(self, db):
        db.execute('CREATE TABLE t (a INT)')
        db.execute('BEGIN')
        db.execute('INSERT INTO t VALUES (1)')
        db.execute('ROLLBACK')
        res = db.execute('SELECT * FROM t')
        assert res == []


class TestWithoutRowid:
    def test_create_without_rowid(self, db):
        res = db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT) WITHOUT ROWID')
        assert res == []

    def test_insert_and_select(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT) WITHOUT ROWID')
        db.execute("INSERT INTO t VALUES (1, 'one')")
        db.execute("INSERT INTO t VALUES (2, 'two')")
        res = db.execute('SELECT * FROM t ORDER BY a')
        assert res == [[1, 'one'], [2, 'two']]

    def test_insert_duplicate_pk(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT) WITHOUT ROWID')
        db.execute("INSERT INTO t VALUES (1, 'one')")
        with pytest.raises(Exception, match='Constraint|UNIQUE|PRIMARY|duplicate'):
            db.execute("INSERT INTO t VALUES (1, 'two')")

    def test_select_where(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT) WITHOUT ROWID')
        db.execute("INSERT INTO t VALUES (1, 'one')")
        db.execute("INSERT INTO t VALUES (2, 'two')")
        res = db.execute("SELECT b FROM t WHERE a = 2")
        assert res == [['two']]

    def test_update_row(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT) WITHOUT ROWID')
        db.execute("INSERT INTO t VALUES (1, 'one')")
        db.execute("INSERT INTO t VALUES (2, 'two')")
        db.execute("UPDATE t SET b = 'updated' WHERE a = 1")
        res = db.execute('SELECT b FROM t ORDER BY a')
        assert res == [['updated'], ['two']]

    def test_delete_row(self, db):
        db.execute('CREATE TABLE t (a INT PRIMARY KEY, b TEXT) WITHOUT ROWID')
        db.execute("INSERT INTO t VALUES (1, 'one')")
        db.execute("INSERT INTO t VALUES (2, 'two')")
        db.execute("DELETE FROM t WHERE a = 1")
        res = db.execute('SELECT * FROM t ORDER BY a')
        assert res == [[2, 'two']]

    def test_text_pk(self, db):
        db.execute('CREATE TABLE t (a TEXT PRIMARY KEY, b INT) WITHOUT ROWID')
        db.execute("INSERT INTO t VALUES ('key1', 10)")
        db.execute("INSERT INTO t VALUES ('key2', 20)")
        res = db.execute('SELECT * FROM t ORDER BY a')
        assert res == [['key1', 10], ['key2', 20]]


class TestGeneratedColumns:
    def test_create_virtual(self, db):
        res = db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 2) VIRTUAL)')
        assert res == []

    def test_create_stored(self, db):
        res = db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 2) STORED)')
        assert res == []

    def test_insert_stored_no_column_list(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 2) STORED)')
        db.execute("INSERT INTO t VALUES (5)")
        res = db.execute('SELECT * FROM t')
        assert res == [[5, 10]]

    def test_insert_stored_explicit_cols(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 2) STORED)')
        db.execute("INSERT INTO t (a) VALUES (7)")
        res = db.execute('SELECT * FROM t')
        assert res == [[7, 14]]

    def test_update_stored_recompute(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 2) STORED)')
        db.execute("INSERT INTO t (a) VALUES (3)")
        db.execute("UPDATE t SET a = 10")
        res = db.execute('SELECT b FROM t')
        assert res == [[20]]

    def test_update_stored_no_change(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 2) STORED)')
        db.execute("INSERT INTO t (a) VALUES (5)")
        db.execute("UPDATE t SET a = 5")
        res = db.execute('SELECT b FROM t')
        assert res == [[10]]

    def test_virtual_in_select(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a + 1) VIRTUAL)')
        db.execute("INSERT INTO t (a) VALUES (10)")
        res = db.execute('SELECT b FROM t')
        assert res == [[11]]

    def test_virtual_in_where(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 3) VIRTUAL)')
        db.execute("INSERT INTO t (a) VALUES (2)")
        db.execute("INSERT INTO t (a) VALUES (5)")
        res = db.execute('SELECT a FROM t WHERE b > 10')
        assert res == [[5]]

    def test_virtual_in_order_by(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * -1) VIRTUAL)')
        db.execute("INSERT INTO t (a) VALUES (3)")
        db.execute("INSERT INTO t (a) VALUES (1)")
        res = db.execute('SELECT a FROM t ORDER BY b')
        assert res == [[3], [1]]

    def test_multiple_generated_cols(self, db):
        db.execute('''
            CREATE TABLE t (
                x INT,
                y INT GENERATED ALWAYS AS (x + 1) STORED,
                z INT GENERATED ALWAYS AS (y * 2) STORED
            )
        ''')
        db.execute("INSERT INTO t (x) VALUES (5)")
        res = db.execute('SELECT * FROM t')
        assert res == [[5, 6, 12]]

    def test_insert_all_columns_explicit(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 2) STORED)')
        db.execute("INSERT INTO t (a, b) VALUES (4, 999)")
        res = db.execute('SELECT * FROM t')
        assert res == [[4, 999]]

    def test_virtual_and_stored_mixed(self, db):
        db.execute('CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a + 1) VIRTUAL, c INT GENERATED ALWAYS AS (b * 2) STORED)')
        db.execute("INSERT INTO t (a) VALUES (3)")
        res = db.execute('SELECT * FROM t')
        assert res == [[3, 4, 8.0]]
