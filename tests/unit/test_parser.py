"""Tests for SQL parser."""

import pytest
from pysqlite.lexer import Lexer
from pysqlite.parser import Parser
from pysqlite.ast import *
from pysqlite.errors import ParseError


def parse(sql: str) -> list[Statement]:
    toks = Lexer(sql).tokenize()
    p = Parser(toks)
    return p.parse()


def test_parse_select_star():
    stmts = parse("SELECT * FROM t")
    assert len(stmts) == 1
    s = stmts[0]
    assert isinstance(s, Select)


def test_parse_select_columns():
    stmts = parse("SELECT a, b + 2 AS c FROM t1")
    s = stmts[0]
    assert len(s.columns) == 2
    assert s.columns[1].alias == 'c'


def test_parse_select_where():
    stmts = parse("SELECT * FROM t WHERE x > 5")
    s = stmts[0]
    assert isinstance(s.where, BinaryOp)
    assert s.where.op == '>'


def test_parse_select_group_by():
    stmts = parse("SELECT COUNT(*) FROM t GROUP BY cat HAVING COUNT(*) > 1")
    s = stmts[0]
    assert len(s.group_by) == 1


def test_parse_select_order_by():
    stmts = parse("SELECT a FROM t ORDER BY b DESC, c ASC")
    s = stmts[0]
    assert len(s.order_by) == 2
    assert s.order_by[0].direction == 'DESC'


def test_parse_select_limit():
    stmts = parse("SELECT * FROM t LIMIT 10 OFFSET 5")
    s = stmts[0]
    assert s.limit is not None


def test_parse_select_distinct():
    stmts = parse("SELECT DISTINCT a FROM t")
    assert stmts[0].distinct


def test_parse_insert_values():
    stmts = parse("INSERT INTO t (a, b) VALUES (1, 'x')")
    s = stmts[0]
    assert isinstance(s, Insert)
    assert s.table.name == 't'
    assert s.columns == ['a', 'b']
    assert len(s.values) == 1
    assert len(s.values[0]) == 2


def test_parse_insert_default():
    stmts = parse("INSERT INTO t DEFAULT VALUES")
    s = stmts[0]
    assert s.default_values


def test_parse_insert_select():
    stmts = parse("INSERT INTO t SELECT * FROM src")
    s = stmts[0]
    assert s.select is not None


def test_parse_update():
    stmts = parse("UPDATE t SET a = 1 WHERE b = 2")
    s = stmts[0]
    assert isinstance(s, Update)
    assert len(s.set_clauses) == 1
    assert s.set_clauses[0].column == 'a'


def test_parse_delete():
    stmts = parse("DELETE FROM t WHERE id = 5")
    s = stmts[0]
    assert isinstance(s, Delete)


def test_parse_create_table():
    stmts = parse("CREATE TABLE t (a INT, b TEXT NOT NULL)")
    s = stmts[0]
    assert isinstance(s, CreateTable)
    assert s.name.name == 't'
    assert len(s.columns) == 2
    assert s.columns[0].name == 'a'
    assert s.columns[1].constraints[0].kind == 'NOT NULL'


def test_parse_create_table_if_not_exists():
    stmts = parse("CREATE TABLE IF NOT EXISTS t (x INT)")
    s = stmts[0]
    assert s.if_not_exists


def test_parse_create_table_as_select():
    stmts = parse("CREATE TABLE t AS SELECT * FROM src")
    s = stmts[0]
    assert s.as_select is not None


def test_parse_create_table_pk():
    stmts = parse("CREATE TABLE t (id INT PRIMARY KEY, name TEXT)")
    s = stmts[0]
    assert s.columns[0].constraints[0].kind == 'PRIMARY KEY'


def test_parse_create_table_without_rowid():
    stmts = parse("CREATE TABLE t (a INT) WITHOUT ROWID")
    s = stmts[0]
    assert s.without_rowid


def test_parse_create_table_strict():
    stmts = parse("CREATE TABLE t (a INT) STRICT")
    s = stmts[0]
    assert s.strict


def test_parse_create_index():
    stmts = parse("CREATE INDEX idx ON t (a, b DESC)")
    s = stmts[0]
    assert isinstance(s, CreateIndex)
    assert s.name == 'idx'
    assert len(s.columns) == 2


def test_parse_create_unique_index():
    stmts = parse("CREATE UNIQUE INDEX idx ON t (a)")
    s = stmts[0]
    assert s.unique


def test_parse_create_view():
    stmts = parse("CREATE VIEW v AS SELECT * FROM t")
    s = stmts[0]
    assert isinstance(s, CreateView)


def test_parse_drop_table():
    stmts = parse("DROP TABLE t")
    s = stmts[0]
    assert isinstance(s, DropTable)
    assert s.name.name == 't'


def test_parse_drop_index():
    stmts = parse("DROP INDEX IF EXISTS idx")
    s = stmts[0]
    assert isinstance(s, DropIndex)
    assert s.if_exists


def test_parse_alter_rename():
    stmts = parse("ALTER TABLE t RENAME TO t2")
    s = stmts[0]
    assert isinstance(s, AlterTable)
    assert s.action == 'RENAME TO'


def test_parse_alter_add_column():
    stmts = parse("ALTER TABLE t ADD COLUMN c INT")
    s = stmts[0]
    assert s.action == 'ADD COLUMN'


def test_parse_begin():
    stmts = parse("BEGIN IMMEDIATE")
    s = stmts[0]
    assert isinstance(s, Begin)
    assert s.mode == 'IMMEDIATE'


def test_parse_commit():
    stmts = parse("COMMIT")
    s = stmts[0]
    assert isinstance(s, Commit)


def test_parse_rollback():
    stmts = parse("ROLLBACK")
    s = stmts[0]
    assert isinstance(s, RollbackStmt)


def test_parse_savepoint():
    stmts = parse("SAVEPOINT sp1")
    s = stmts[0]
    assert isinstance(s, Savepoint)
    assert s.name == 'sp1'


def test_parse_release():
    stmts = parse("RELEASE SAVEPOINT sp1")
    s = stmts[0]
    assert isinstance(s, Release)


def test_parse_pragma():
    stmts = parse("PRAGMA page_count")
    s = stmts[0]
    assert isinstance(s, Pragma)


def test_parse_analyze():
    stmts = parse("ANALYZE")
    s = stmts[0]
    assert isinstance(s, Analyze)


def test_parse_vacuum():
    stmts = parse("VACUUM")
    s = stmts[0]
    assert isinstance(s, Vacuum)


def test_parse_explain():
    stmts = parse("EXPLAIN SELECT * FROM t")
    s = stmts[0]
    assert isinstance(s, Explain)


def test_parse_explain_query_plan():
    stmts = parse("EXPLAIN QUERY PLAN SELECT * FROM t")
    s = stmts[0]
    assert s.query_plan


def test_parse_with_cte():
    stmts = parse("WITH cte AS (SELECT 1) SELECT * FROM cte")
    s = stmts[0]
    assert isinstance(s, Select)
    assert len(s.ctes) == 1


def test_parse_recursive_cte():
    stmts = parse("WITH RECURSIVE cte(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM cte WHERE n<10) SELECT * FROM cte")
    s = stmts[0]
    assert len(s.ctes) == 1
    assert s.ctes[0].recursive


def test_parse_join():
    stmts = parse("SELECT * FROM t1 JOIN t2 ON t1.id = t2.id")
    s = stmts[0]
    assert len(s.from_clause) > 0


def test_parse_left_join():
    stmts = parse("SELECT * FROM t1 LEFT JOIN t2 ON t1.id = t2.id")
    s = stmts[0]
    assert isinstance(s.from_clause[0], JoinClause)


def test_parse_cross_join():
    stmts = parse("SELECT * FROM t1 CROSS JOIN t2")
    s = stmts[0]
    assert isinstance(s.from_clause[0], JoinClause)


def test_parse_subquery_from():
    stmts = parse("SELECT * FROM (SELECT * FROM t) AS sub")
    s = stmts[0]
    assert len(s.from_clause) > 0


def test_parse_case_expression():
    stmts = parse("SELECT CASE WHEN x > 0 THEN 'pos' ELSE 'neg' END FROM t")
    s = stmts[0]
    assert isinstance(s.columns[0].expr, CaseExpr)


def test_parse_cast_expression():
    stmts = parse("SELECT CAST(a AS TEXT) FROM t")
    s = stmts[0]
    assert isinstance(s.columns[0].expr, CastExpr)


def test_parse_exists():
    stmts = parse("SELECT * FROM t WHERE EXISTS (SELECT 1 FROM u)")
    s = stmts[0]
    assert isinstance(s.where, ExistsSubquery)


def test_parse_in_list():
    stmts = parse("SELECT * FROM t WHERE x IN (1, 2, 3)")
    s = stmts[0]
    assert isinstance(s.where, InOp)


def test_parse_in_subquery():
    stmts = parse("SELECT * FROM t WHERE x IN (SELECT x FROM u)")
    s = stmts[0]
    assert isinstance(s.where, InOp)
    assert s.where.select is not None


def test_parse_between():
    stmts = parse("SELECT * FROM t WHERE x BETWEEN 1 AND 10")
    s = stmts[0]
    assert isinstance(s.where, BetweenOp)


def test_parse_is_null():
    stmts = parse("SELECT * FROM t WHERE x IS NULL")
    s = stmts[0]
    assert isinstance(s.where, IsNullOp)


def test_parse_is_not_null():
    stmts = parse("SELECT * FROM t WHERE x IS NOT NULL")
    s = stmts[0]
    assert isinstance(s.where, IsNullOp)
    assert s.where.negated


def test_parse_like():
    stmts = parse("SELECT * FROM t WHERE name LIKE '%foo%'")
    s = stmts[0]
    assert isinstance(s.where, LikeOp)


def test_parse_function_no_args():
    stmts = parse("SELECT random()")
    s = stmts[0]
    assert isinstance(s.columns[0].expr, FunctionCall)
    assert s.columns[0].expr.name == 'random'


def test_parse_function_args():
    stmts = parse("SELECT MAX(a, b) FROM t")
    s = stmts[0]
    assert len(s.columns[0].expr.args) == 2


def test_parse_count_star():
    stmts = parse("SELECT COUNT(*) FROM t")
    s = stmts[0]
    assert s.columns[0].expr.star


def test_parse_distinct_count():
    stmts = parse("SELECT COUNT(DISTINCT a) FROM t")
    s = stmts[0]
    assert s.columns[0].expr.distinct


def test_parse_window_function():
    stmts = parse("SELECT ROW_NUMBER() OVER (PARTITION BY cat ORDER BY val) FROM t")
    s = stmts[0]
    fn = s.columns[0].expr
    assert isinstance(fn, FunctionCall)
    assert fn.over is not None


def test_parse_on_conflict_do_nothing():
    stmts = parse("INSERT INTO t (a) VALUES (1) ON CONFLICT DO NOTHING")
    s = stmts[0]
    assert s.on_conflict is not None
    assert s.on_conflict.action == 'NOTHING'


def test_parse_on_conflict_do_update():
    stmts = parse("INSERT INTO t (a) VALUES (1) ON CONFLICT(a) DO UPDATE SET a = excluded.a")
    s = stmts[0]
    assert s.on_conflict is not None
    assert s.on_conflict.action == 'UPDATE'


def test_parse_returning():
    stmts = parse("INSERT INTO t (a) VALUES (1) RETURNING a, b")
    s = stmts[0]
    assert s.returning is not None
    assert len(s.returning.columns) == 2


def test_parse_update_returning():
    stmts = parse("UPDATE t SET a = 1 RETURNING a")
    s = stmts[0]
    assert s.returning is not None


def test_parse_delete_returning():
    stmts = parse("DELETE FROM t RETURNING *")
    s = stmts[0]
    assert s.returning is not None


def test_parse_multiple_statements():
    stmts = parse("SELECT 1; SELECT 2")
    assert len(stmts) == 2


def test_parse_insert_with_upsert():
    stmts = parse("""
        INSERT INTO t (a, b) VALUES (1, 2)
        ON CONFLICT(a) WHERE a > 0 DO UPDATE SET b = excluded.b WHERE excluded.b > 0
        RETURNING a
    """)
    s = stmts[0]
    assert s.on_conflict is not None
    assert s.returning is not None


def test_parse_table_constraint_pk():
    stmts = parse("CREATE TABLE t (a INT, b INT, PRIMARY KEY (a, b))")
    s = stmts[0]
    assert len(s.constraints) == 1
    assert s.constraints[0].kind == 'PRIMARY KEY'


def test_parse_table_constraint_fk():
    stmts = parse("CREATE TABLE t (a INT, FOREIGN KEY (a) REFERENCES other(id))")
    s = stmts[0]
    assert len(s.constraints) == 1


def test_parse_compound_select():
    stmts = parse("SELECT a FROM t1 UNION ALL SELECT b FROM t2")
    s = stmts[0]
    assert s.compound_op == 'UNION'


def test_parse_ordering_term_nulls():
    stmts = parse("SELECT * FROM t ORDER BY a DESC NULLS LAST")
    s = stmts[0]
    assert s.order_by[0].nulls == 'LAST'


def test_parse_operator_precedence():
    """Verify that 'a + b * c' parses as a + (b * c), not (a + b) * c."""
    stmts = parse("SELECT a + b * c FROM t")
    s = stmts[0]
    expr = s.columns[0].expr
    assert isinstance(expr, BinaryOp)
    assert expr.op == '+'
    assert isinstance(expr.right, BinaryOp)
    assert expr.right.op == '*'


def test_parse_column_ref_with_table():
    stmts = parse("SELECT t.a FROM t")
    s = stmts[0]
    col = s.columns[0].expr
    assert isinstance(col, ColumnRef)
    assert col.table == 't'
    assert col.name == 'a'


def test_parse_exists_subquery_in_where():
    stmts = parse("SELECT * FROM t WHERE NOT EXISTS (SELECT 1 FROM u)")
    s = stmts[0]
    # NOT EXISTS -> UnaryOp('NOT', ExistsSubquery(...))
    assert isinstance(s.where, UnaryOp)
    assert s.where.op == 'NOT'
    assert isinstance(s.where.operand, ExistsSubquery)
