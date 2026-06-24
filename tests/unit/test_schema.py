"""Tests for the schema manager."""

from pysqlite.schema import (
    Schema, TableDef, ColumnDef, IndexDef, IndexedColumnDef,
    ViewDef, TriggerDef, Collation,
    AFFINITY, _collation_binary, _collation_nocase, _collation_rtrim,
)
from pysqlite.pager import Pager
from pysqlite.vfs import MemoryVFS
from pysqlite.ast import TypeName


def make_pager():
    return Pager(MemoryVFS(), ':memory:')


def test_affinity_integer():
    assert Schema._determine_affinity(TypeName('INT')) == AFFINITY.INTEGER
    assert Schema._determine_affinity(TypeName('INTEGER')) == AFFINITY.INTEGER
    assert Schema._determine_affinity(TypeName('BIGINT')) == AFFINITY.INTEGER
    assert Schema._determine_affinity(TypeName('SMALLINT')) == AFFINITY.INTEGER
    assert Schema._determine_affinity(TypeName('TINYINT')) == AFFINITY.INTEGER
    assert Schema._determine_affinity(TypeName('BOOLEAN')) == AFFINITY.INTEGER


def test_affinity_text():
    assert Schema._determine_affinity(TypeName('TEXT')) == AFFINITY.TEXT
    assert Schema._determine_affinity(TypeName('VARCHAR')) == AFFINITY.TEXT
    assert Schema._determine_affinity(TypeName('CHAR')) == AFFINITY.TEXT
    assert Schema._determine_affinity(TypeName('CLOB')) == AFFINITY.TEXT


def test_affinity_real():
    assert Schema._determine_affinity(TypeName('REAL')) == AFFINITY.REAL
    assert Schema._determine_affinity(TypeName('FLOAT')) == AFFINITY.REAL
    assert Schema._determine_affinity(TypeName('DOUBLE')) == AFFINITY.REAL


def test_affinity_numeric():
    assert Schema._determine_affinity(TypeName('NUMERIC')) == AFFINITY.NUMERIC
    assert Schema._determine_affinity(TypeName('DECIMAL')) == AFFINITY.NUMERIC


def test_affinity_blob():
    assert Schema._determine_affinity(TypeName('BLOB')) == AFFINITY.BLOB
    assert Schema._determine_affinity(None) == AFFINITY.BLOB
    assert Schema._determine_affinity(TypeName('')) == AFFINITY.BLOB


def test_affinity_unknown():
    assert Schema._determine_affinity(TypeName('FOO')) == AFFINITY.BLOB


def test_table_def_defaults():
    td = TableDef(name='test')
    assert td.name == 'test'
    assert td.root_page == 0
    assert td.columns == []
    assert not td.without_rowid
    assert not td.strict


def test_table_def_with_columns():
    col = ColumnDef(name='id', affinity=AFFINITY.INTEGER, primary_key=True)
    td = TableDef(name='t', columns=[col])
    assert td.primary_key_columns() == ['id']
    assert td.column_index('id') == 0
    assert td.has_autoinc() is False


def test_table_def_autoinc():
    col = ColumnDef(name='id', affinity=AFFINITY.INTEGER,
                    primary_key=True, auto_increment=True)
    td = TableDef(name='t', columns=[col])
    assert td.has_autoinc()


def test_index_def():
    idx = IndexDef(name='idx_t_a', table_name='t',
                   columns=[IndexedColumnDef(name='a')],
                   unique=True)
    assert idx.name == 'idx_t_a'
    assert idx.table_name == 't'
    assert len(idx.columns) == 1
    assert idx.columns[0].name == 'a'
    assert idx.unique


def test_view_def():
    v = ViewDef(name='myview', sql='SELECT 1')
    assert v.name == 'myview'
    assert v.sql == 'SELECT 1'


def test_trigger_def():
    tr = TriggerDef(name='mytrig', table_name='t',
                    sql='CREATE TRIGGER ...', time='BEFORE', event='INSERT')
    assert tr.name == 'mytrig'
    assert tr.table_name == 't'


def test_collation_binary():
    assert _collation_binary('a', 'b') == -1
    assert _collation_binary('b', 'a') == 1
    assert _collation_binary('a', 'a') == 0
    assert _collation_binary('A', 'a') != 0  # case-sensitive


def test_collation_nocase():
    assert _collation_nocase('A', 'a') == 0
    assert _collation_nocase('a', 'A') == 0
    assert _collation_nocase('abc', 'ABC') == 0


def test_collation_rtrim():
    assert _collation_rtrim('a  ', 'a') == 0
    assert _collation_rtrim('a', 'a  ') == 0
    assert _collation_rtrim('ab', 'a') != 0


def test_collation_class():
    c = Collation('MYCOLL', _collation_binary)
    assert c.name == 'MYCOLL'
    assert c.compare('a', 'b') == -1


def test_schema_default_collations():
    pager = make_pager()
    schema = Schema(pager)
    assert 'BINARY' in schema.collations
    assert 'NOCASE' in schema.collations
    assert 'RTRIM' in schema.collations


def test_schema_load_empty():
    pager = make_pager()
    schema = Schema(pager)
    # Initialize database header so page 1 is readable
    pager._init_header()
    schema.load()
    assert schema.tables == {}
    assert schema.indexes == {}


def test_schema_add_drop_table():
    pager = make_pager()
    schema = Schema(pager)
    td = TableDef(name='t', root_page=2)
    schema.add_table(td)
    assert 't' in schema.tables
    schema.drop_table('t')
    assert 't' not in schema.tables


def test_schema_add_drop_index():
    pager = make_pager()
    schema = Schema(pager)
    idx = IndexDef(name='idx_t_a', table_name='t')
    schema.add_index(idx)
    assert 'idx_t_a' in schema.indexes
    schema.drop_index('idx_t_a')
    assert 'idx_t_a' not in schema.indexes


def test_schema_cookie_version():
    pager = make_pager()
    schema = Schema(pager)
    v1 = schema.schema_cookie
    schema.add_table(TableDef(name='t'))
    assert schema.schema_cookie > v1


def test_schema_verify_cookie():
    pager = make_pager()
    schema = Schema(pager)
    expected = schema.schema_cookie
    assert schema.verify_cookie(expected)
    schema.add_table(TableDef(name='t'))
    assert not schema.verify_cookie(expected)


def test_schema_get_table_indexes():
    pager = make_pager()
    schema = Schema(pager)
    schema.add_table(TableDef(name='t'))
    schema.add_index(IndexDef(name='idx_t_a', table_name='t'))
    schema.add_index(IndexDef(name='idx_t_b', table_name='t'))
    schema.add_index(IndexDef(name='idx_other', table_name='other'))
    idxs = schema.get_table_indexes('t')
    assert len(idxs) == 2


def test_schema_parse_create_table():
    sql = 'CREATE TABLE t (a INT, b TEXT NOT NULL, c REAL DEFAULT 0.0)'
    pager = make_pager()
    schema = Schema(pager)
    td = schema._parse_create_table('t', 2, sql)
    assert td.name == 't'
    assert td.root_page == 2
    assert len(td.columns) == 3
    assert td.columns[0].name == 'a'
    assert td.columns[0].affinity == AFFINITY.INTEGER
    assert td.columns[1].name == 'b'
    assert td.columns[1].affinity == AFFINITY.TEXT
    assert td.columns[1].not_null
    assert td.columns[2].name == 'c'
    assert td.columns[2].affinity == AFFINITY.REAL


def test_schema_drop_table_cascades_indexes():
    pager = make_pager()
    schema = Schema(pager)
    schema.add_table(TableDef(name='t'))
    schema.add_index(IndexDef(name='idx_t_a', table_name='t'))
    schema.drop_table('t')
    assert schema.get_table_indexes('t') == []
