"""Tests for SQL lexer."""

import pytest
from pysqlite.lexer import Lexer, TokenType, LexerError


def tokenize(sql: str):
    return Lexer(sql).tokenize()


def test_empty():
    toks = tokenize("")
    assert len(toks) == 1
    assert toks[0].type == TokenType.EOF


def test_semicolon():
    toks = tokenize(";")
    assert len(toks) == 2
    assert toks[0].type == TokenType.SEMI


def test_keyword_select():
    toks = tokenize("SELECT")
    assert toks[0].type == TokenType.SELECT


def test_keyword_case_insensitive():
    toks = tokenize("select Select SELECT")
    assert all(t.type == TokenType.SELECT for t in toks[:3])


def test_identifier():
    toks = tokenize("my_table")
    assert toks[0].type == TokenType.IDENTIFIER
    assert toks[0].value == "my_table"


def test_integer():
    toks = tokenize("42")
    assert toks[0].type == TokenType.INTEGER
    assert toks[0].value == "42"


def test_float():
    toks = tokenize("3.14")
    assert toks[0].type == TokenType.FLOAT


def test_scientific_float():
    toks = tokenize("1.5e10")
    assert toks[0].type == TokenType.FLOAT


def test_string():
    toks = tokenize("'hello world'")
    assert toks[0].type == TokenType.STRING
    assert toks[0].value == "'hello world'"


def test_string_escape():
    toks = tokenize("'it''s'")
    assert toks[0].type == TokenType.STRING


def test_quoted_id():
    toks = tokenize('"column name"')
    assert toks[0].type == TokenType.QUOTED_ID


def test_bracket_id():
    toks = tokenize("[table]")
    assert toks[0].type == TokenType.BRACKET_ID


def test_backtick_id():
    toks = tokenize("`field`")
    assert toks[0].type == TokenType.BACKTICK_ID


def test_blob():
    toks = tokenize("x'deadbeef'")
    assert toks[0].type == TokenType.BLOB


def test_line_comment():
    toks = tokenize("SELECT -- comment\nFROM")
    assert toks[0].type == TokenType.SELECT
    assert toks[1].type == TokenType.FROM


def test_block_comment():
    toks = tokenize("SELECT /* block */ FROM")
    assert toks[0].type == TokenType.SELECT
    assert toks[1].type == TokenType.FROM


def test_operators():
    sql = "+ - * / % & | ~ < > = == <> != || << >> -> ->>"
    toks = tokenize(sql)
    types = [t.type for t in toks[:-1]]
    assert types == [
        TokenType.PLUS, TokenType.MINUS, TokenType.STAR, TokenType.SLASH,
        TokenType.PERCENT, TokenType.AMPERSAND, TokenType.PIPE, TokenType.TILDE,
        TokenType.LT, TokenType.GT, TokenType.EQ, TokenType.EQ2,
        TokenType.NE, TokenType.NE2, TokenType.CONCAT, TokenType.LSHIFT,
        TokenType.RSHIFT, TokenType.ARROW, TokenType.ARROW2,
    ]


def test_punctuation():
    sql = "( ) . , ;"
    toks = tokenize(sql)
    types = [t.type for t in toks[:-1]]
    assert types == [
        TokenType.LPAREN, TokenType.RPAREN, TokenType.DOT, TokenType.COMMA, TokenType.SEMI,
    ]


def test_complex_select():
    sql = "SELECT a, b + 2 AS c FROM t WHERE d = 'x'"
    toks = tokenize(sql)
    types = [t.type for t in toks[:-1]]
    assert types == [
        TokenType.SELECT, TokenType.IDENTIFIER, TokenType.COMMA,
        TokenType.IDENTIFIER, TokenType.PLUS, TokenType.INTEGER,
        TokenType.AS, TokenType.IDENTIFIER,
        TokenType.FROM, TokenType.IDENTIFIER,
        TokenType.WHERE, TokenType.IDENTIFIER, TokenType.EQ, TokenType.STRING,
    ]


def test_keywords():
    sql = "CREATE TABLE DROP INDEX VIEW TRIGGER INSERT UPDATE DELETE FROM WHERE JOIN ON AS AND OR NOT IN BETWEEN LIKE IS NULL EXISTS CASE WHEN THEN ELSE END CAST GROUP BY ORDER ASC DESC LIMIT OFFSET DISTINCT ALL UNION INTERSECT EXCEPT BEGIN COMMIT ROLLBACK"
    toks = tokenize(sql)
    types = [t.type for t in toks[:-1]]
    assert len(types) == 44


def test_unexpected_character():
    with pytest.raises(LexerError):
        tokenize("SELECT #foo")


def test_positions():
    sql = "SELECT\n  a\n"
    toks = tokenize(sql)
    kw = toks[0]
    assert kw.line == 1
    assert kw.col == 1
    ident = toks[1]
    assert ident.line == 2
    assert ident.col == 3


def test_all_sqlite_keywords():
    sql = " ".join([
        "ABORT", "ACTION", "ADD", "AFTER", "ALL", "ALTER", "ALWAYS", "ANALYZE",
        "AND", "AS", "ASC", "AUTOINCREMENT", "BEFORE", "BEGIN", "BETWEEN", "BY",
        "CASCADE", "CASE", "CAST", "CHECK", "COLLATE", "COLUMN", "COMMIT",
        "CONFLICT", "CONSTRAINT", "CREATE", "CROSS", "CURRENT", "DATABASE",
        "DEFAULT", "DEFERRED", "DELETE", "DESC", "DETACH", "DISTINCT", "DO",
        "DROP", "EACH", "ELSE", "END", "ESCAPE", "EXCEPT", "EXCLUSIVE",
        "EXISTS", "EXPLAIN", "FAIL", "FILTER", "FIRST", "FOLLOWING", "FOR",
        "FOREIGN", "FROM", "FULL", "GENERATED", "GLOB", "GROUP", "HAVING",
        "IF", "IGNORE", "IMMEDIATE", "IN", "INDEX", "INITIALLY", "INNER",
        "INSERT", "INSTEAD", "INTERSECT", "INTO", "IS", "JOIN", "KEY", "LAST",
        "LEFT", "LIKE", "LIMIT", "MATCH", "NATURAL", "NO", "NOT", "NOTHING",
        "NULL", "OF", "OFFSET", "ON", "OR", "ORDER", "OUTER", "OVER",
        "PARTITION", "PLAN", "PRAGMA", "PRECEDING", "PRIMARY", "QUERY",
        "RAISE", "RANGE", "RECURSIVE", "REFERENCES", "REGEXP", "REINDEX",
        "RELEASE", "RENAME", "REPLACE", "RESTRICT", "RETURNING", "RIGHT",
        "ROLLBACK", "ROW", "ROWS", "SAVEPOINT", "SELECT", "SET", "STORED",
        "STRICT", "TABLE", "TEMP", "TEMPORARY", "THEN", "TIES", "TO",
        "TRANSACTION", "TRIGGER", "TRUNCATE", "UNBOUNDED", "UNION", "UNIQUE",
        "UPDATE", "USING", "VACUUM", "VALUES", "VIEW", "VIRTUAL", "WHEN",
        "WHERE", "WINDOW", "WITH", "WITHOUT",
    ])
    toks = tokenize(sql)
    assert len(toks) == 138  # 137 words + EOF
