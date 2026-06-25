"""Schema manager — loads/saves sqlite_schema, provides table/index metadata."""

from dataclasses import dataclass, field
from typing import Any, Callable

from pysqlite.btree import BTree
from pysqlite.record import Record
from pysqlite.lexer import Lexer
from pysqlite.parser import Parser
from pysqlite.ast import (
    Expr, Statement,
    CreateTable, CreateIndex, CreateView, CreateTrigger,
    TableName, ColumnDef as AstColumnDef, ColumnConstraint,
    TableConstraint, TypeName,
    Select,
)
from pysqlite.errors import DatabaseError


# ── Affinity constants ──

class AFFINITY:
    INTEGER = 0
    REAL = 1
    NUMERIC = 2
    TEXT = 3
    BLOB = 4


# ── Data structures ──

@dataclass
class IndexedColumnDef:
    name: str
    collation: str | None = None
    order: str = 'ASC'
    expr: Expr | None = None


@dataclass
class ColumnDef:
    name: str
    type_name: TypeName | None = None
    affinity: int = AFFINITY.BLOB
    not_null: bool = False
    primary_key: bool = False
    unique: bool = False
    default_value: Any = None
    auto_increment: bool = False
    collation: str | None = None
    is_generated: bool = False
    generated_expr: Expr | None = None
    generated_type: str | None = None


@dataclass
class IndexDef:
    name: str
    table_name: str
    root_page: int = 0
    columns: list[IndexedColumnDef] = field(default_factory=list)
    unique: bool = False
    partial: bool = False
    partial_where: Expr | None = None
    sql: str = ''


@dataclass
class TableDef:
    name: str
    root_page: int = 0
    columns: list[ColumnDef] = field(default_factory=list)
    constraints: list[TableConstraint] = field(default_factory=list)
    indexes: list[IndexDef] = field(default_factory=list)
    foreign_keys: list = field(default_factory=list)
    without_rowid: bool = False
    strict: bool = False
    sql: str = ''

    def has_autoinc(self) -> bool:
        return any(c.auto_increment for c in self.columns)

    def primary_key_columns(self) -> list[str]:
        pk = [c.name for c in self.columns if c.primary_key]
        if not pk:
            for tc in self.constraints:
                if tc.kind == 'PRIMARY KEY':
                    pk = tc.columns or []
                    break
        return pk

    def column_index(self, name: str) -> int:
        for i, c in enumerate(self.columns):
            if c.name.upper() == name.upper():
                return i
        raise ValueError(f'Column {name} not found in {self.name}')


@dataclass
class ViewDef:
    name: str
    sql: str
    select: Select | None = None


@dataclass
class TriggerDef:
    name: str
    table_name: str
    sql: str
    time: str = 'BEFORE'
    event: str = 'INSERT'
    programs: list = field(default_factory=list)
    parsed_ast: Any = None


# ── Collation ──

class Collation:
    def __init__(self, name: str, func: Callable[[str, str], int]):
        self.name = name
        self.func = func

    def compare(self, a: str, b: str) -> int:
        return self.func(a, b)


def _collation_binary(a: str, b: str) -> int:
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _collation_nocase(a: str, b: str) -> int:
    return _collation_binary(a.upper(), b.upper())


def _collation_rtrim(a: str, b: str) -> int:
    return _collation_binary(a.rstrip(), b.rstrip())


# ── Schema Manager ──

class Schema:
    def __init__(self, pager):
        self.pager = pager
        self.tables: dict[str, TableDef] = {}
        self.indexes: dict[str, IndexDef] = {}
        self.views: dict[str, ViewDef] = {}
        self.triggers: dict[str, TriggerDef] = {}
        self.collations: dict[str, Collation] = {
            'BINARY': Collation('BINARY', _collation_binary),
            'NOCASE': Collation('NOCASE', _collation_nocase),
            'RTRIM': Collation('RTRIM', _collation_rtrim),
        }
        self.schema_version = 0
        self.schema_cookie = 0

    # ── Load ──

    def load(self):
        self.tables.clear()
        self.indexes.clear()
        self.views.clear()
        self.triggers.clear()
        self._ensure_schema_page()
        btree = BTree(self.pager, 1, is_table=True)
        cursor = btree.cursor()
        try:
            cursor.first()
        except Exception:
            return
        while not cursor.eof:
            try:
                payload = cursor.current_payload()
                record, _ = Record.decode(payload)
                values = record.get_values()
                type_, name, tbl_name, rootpage, sql = values
                self._register_object(type_, name, tbl_name, rootpage, sql)
            except Exception:
                pass
            cursor.next()

    def _ensure_schema_page(self):
        """Ensure page 1 is a valid leaf-table B-Tree page with header offset."""
        try:
            raw = self.pager.read_page(1)
        except Exception:
            return
        # Check if page 1 has a valid B-Tree leaf table header at byte 100
        if len(raw) < 101:
            return
        page_type = raw[100]
        if page_type in (0x0D, 0x05):
            return  # Already initialized
        # Initialize page 1 as an empty leaf table page
        raw[100] = 0x0D  # PT_LEAF_TABLE
        raw[101:103] = (0).to_bytes(2, 'big')  # first_freeblock = 0
        raw[103:105] = (0).to_bytes(2, 'big')  # cell_count = 0
        raw[105:107] = self.pager.page_size.to_bytes(2, 'big')  # cell_content_offset = page_size
        raw[107] = 0  # fragmented_free_bytes = 0
        self.pager.write_page(1, bytes(raw))

    def _register_object(self, type_: str, name: str, tbl_name: str,
                         rootpage: int, sql: str):
        if type_ == 'table':
            self.tables[name] = self._parse_create_table(name, rootpage, sql)
        elif type_ == 'index':
            self.indexes[name] = self._parse_create_index(name, tbl_name, rootpage, sql)
        elif type_ == 'view':
            select = self._extract_select(sql)
            self.views[name] = ViewDef(name, sql, select)
        elif type_ == 'trigger':
            self.triggers[name] = self._parse_create_trigger(name, tbl_name, sql)

    # ── Save ──

    def save(self):
        self._ensure_schema_page()
        btree = BTree(self.pager, 1, is_table=True)
        self._clear_schema(btree)
        for table in self.tables.values():
            self._insert_schema_entry(btree, 'table', table.name,
                                      table.name, table.root_page, table.sql)
        for index in self.indexes.values():
            self._insert_schema_entry(btree, 'index', index.name,
                                      index.table_name, index.root_page, index.sql)
        for view in self.views.values():
            self._insert_schema_entry(btree, 'view', view.name,
                                      view.name, 0, view.sql)
        for trigger in self.triggers.values():
            self._insert_schema_entry(btree, 'trigger', trigger.name,
                                      trigger.table_name, 0, trigger.sql)

    def _clear_schema(self, btree):
        cursor = btree.cursor()
        cursor.first()
        while not cursor.eof:
            cursor.delete()
            cursor.first()

    def _insert_schema_entry(self, btree, type_: str, name: str,
                             tbl_name: str, rootpage: int, sql: str):
        from pysqlite.record import Record as RecordEncoder
        values = [type_, name, tbl_name, rootpage, sql]
        columns = [(RecordEncoder.serial_type(v), v) for v in values]
        rec = RecordEncoder(columns)
        payload = rec.encode()
        rowid = hash(name) & 0x7FFFFFFF
        cursor = btree.cursor()
        cursor.insert(rowid, rowid, payload)

    # ── Lookups ──

    def get_table(self, name: str, schema_name: str | None = None) -> TableDef | None:
        return self.tables.get(name)

    def get_index(self, name: str) -> IndexDef | None:
        return self.indexes.get(name)

    def get_view(self, name: str) -> ViewDef | None:
        return self.views.get(name)

    def get_trigger(self, name: str) -> TriggerDef | None:
        return self.triggers.get(name)

    def get_table_indexes(self, table_name: str) -> list[IndexDef]:
        return [idx for idx in self.indexes.values()
                if idx.table_name == table_name]

    def add_table(self, table_def: TableDef):
        self.tables[table_def.name] = table_def
        self._bump_cookie()

    def drop_table(self, name: str):
        self.tables.pop(name, None)
        self.indexes = {k: v for k, v in self.indexes.items()
                        if v.table_name != name}
        self._bump_cookie()

    def add_index(self, index_def: IndexDef):
        self.indexes[index_def.name] = index_def
        self._bump_cookie()

    def drop_index(self, name: str):
        self.indexes.pop(name, None)
        self._bump_cookie()

    def add_view(self, view_def: ViewDef):
        self.views[view_def.name] = view_def
        self._bump_cookie()

    def drop_view(self, name: str):
        self.views.pop(name, None)
        self._bump_cookie()

    def _bump_cookie(self):
        self.schema_cookie += 1
        self.schema_version += 1

    # ── Parsing from SQL ──

    def _parse_create_table(self, name: str, rootpage: int, sql: str) -> TableDef:
        try:
            tokens = Lexer(sql).tokenize()
            parser = Parser(tokens)
            stmts = parser.parse()
        except Exception:
            return TableDef(name=name, root_page=rootpage, sql=sql)

        stmt = None
        for s in stmts:
            if isinstance(s, CreateTable):
                stmt = s
                break
        if stmt is None:
            return TableDef(name=name, root_page=rootpage, sql=sql)

        columns = []
        for col_def in stmt.columns:
            affinity = self._determine_affinity(col_def.type_name)
            columns.append(ColumnDef(
                name=col_def.name,
                type_name=col_def.type_name,
                affinity=affinity,
                not_null=self._has_constraint(col_def, 'NOT NULL'),
                primary_key=self._has_constraint(col_def, 'PRIMARY KEY'),
                unique=self._has_constraint(col_def, 'UNIQUE'),
                default_value=self._get_default(col_def),
                auto_increment=self._has_autoinc(col_def),
                collation=self._get_collation(col_def),
            ))
        return TableDef(
            name=name, root_page=rootpage, columns=columns,
            constraints=stmt.constraints,
            without_rowid=stmt.without_rowid, strict=stmt.strict,
            sql=sql,
        )

    def _parse_create_index(self, name: str, tbl_name: str,
                            rootpage: int, sql: str) -> IndexDef:
        try:
            tokens = Lexer(sql).tokenize()
            parser = Parser(tokens)
            stmts = parser.parse()
        except Exception:
            return IndexDef(name=name, table_name=tbl_name, root_page=rootpage, sql=sql)
        stmt = None
        for s in stmts:
            if isinstance(s, CreateIndex):
                stmt = s
                break
        if stmt is None:
            return IndexDef(name=name, table_name=tbl_name, root_page=rootpage, sql=sql)
        columns = []
        for ot in stmt.columns:
            columns.append(IndexedColumnDef(
                name=ot.expr.value if hasattr(ot.expr, 'value') else str(ot.expr),
                order=ot.direction,
            ))
        return IndexDef(
            name=name, table_name=tbl_name, root_page=rootpage,
            columns=columns, unique=stmt.unique,
            partial=stmt.where is not None, sql=sql,
        )

    def _parse_create_trigger(self, name: str, tbl_name: str, sql: str) -> TriggerDef:
        try:
            tokens = Lexer(sql).tokenize()
            parser = Parser(tokens)
            stmts = parser.parse()
        except Exception:
            return TriggerDef(name=name, table_name=tbl_name, sql=sql)

        stmt = None
        for s in stmts:
            if isinstance(s, CreateTrigger):
                stmt = s
                break
        if stmt is None:
            return TriggerDef(name=name, table_name=tbl_name, sql=sql)

        stmt.name = name
        from pysqlite.compile import Compiler
        programs = []
        for body_stmt in stmt.statements:
            compiler = Compiler(self, self.pager)
            prog = compiler.compile(body_stmt)
            programs.append(prog)

        return TriggerDef(
            name=name, table_name=tbl_name, sql=sql,
            time=stmt.time, event=stmt.event,
            programs=programs, parsed_ast=stmt,
        )

    def _extract_select(self, sql: str) -> Select | None:
        try:
            tokens = Lexer(sql).tokenize()
            parser = Parser(tokens)
            stmts = parser.parse()
            for s in stmts:
                if isinstance(s, CreateView):
                    return s.select
        except Exception:
            pass
        return None

    # ── Helper methods ──

    @staticmethod
    def _determine_affinity(type_name: TypeName | None) -> int:
        if type_name is None or not type_name.name:
            return AFFINITY.BLOB
        name = type_name.name.upper()
        if any(kw in name for kw in ('INT', 'TINY', 'SMALL', 'MEDIUM', 'BIG',
                                      'UNSIGNED', 'BOOLEAN', 'BIT')):
            return AFFINITY.INTEGER
        if any(kw in name for kw in ('REAL', 'FLOAT', 'DOUBLE', 'NUMERIC', 'DECIMAL')):
            if name in ('NUMERIC', 'DECIMAL'):
                return AFFINITY.NUMERIC
            return AFFINITY.REAL
        if any(kw in name for kw in ('CHAR', 'CLOB', 'TEXT', 'VARCHAR', 'VARYING',
                                      'NCHAR', 'NVARCHAR', 'NATIONAL', 'DATE', 'DATETIME')):
            return AFFINITY.TEXT
        if name == 'BLOB' or not name:
            return AFFINITY.BLOB
        if name in ('NUMERIC', 'DECIMAL', 'BOOLEAN', 'DATE', 'DATETIME'):
            return AFFINITY.NUMERIC
        return AFFINITY.BLOB

    @staticmethod
    def _has_constraint(col_def: AstColumnDef, kind: str) -> bool:
        return any(c.kind == kind for c in col_def.constraints)

    @staticmethod
    def _has_autoinc(col_def: AstColumnDef) -> bool:
        return any(c.kind == 'PRIMARY KEY' and c.details == 'AUTOINCREMENT'
                   for c in col_def.constraints) or \
               any(getattr(c, 'auto_increment', False) for c in col_def.constraints)

    @staticmethod
    def _get_default(col_def: AstColumnDef) -> Any:
        for c in col_def.constraints:
            if c.kind == 'DEFAULT':
                return c.details
        return None

    @staticmethod
    def _get_collation(col_def: AstColumnDef) -> str | None:
        for c in col_def.constraints:
            if c.kind == 'COLLATE':
                return c.details
        return None

    # ── Schema version ──

    def increment_version(self):
        self.schema_cookie += 1
        self.schema_version += 1

    def verify_cookie(self, expected: int) -> bool:
        return self.schema_cookie == expected
