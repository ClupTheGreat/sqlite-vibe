"""AST node classes for SQL statements, expressions, and schema objects."""

from dataclasses import dataclass, field
from typing import Any


class Statement:
    pass


class Expr:
    pass


# ── Expressions ──

@dataclass
class Literal(Expr):
    value: Any


@dataclass
class NullLiteral(Expr):
    pass


@dataclass
class ColumnRef(Expr):
    name: str
    table: str | None = None
    schema: str | None = None


@dataclass
class UnaryOp(Expr):
    op: str
    operand: Expr


@dataclass
class BinaryOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class FunctionCall(Expr):
    name: str
    args: list[Expr] = field(default_factory=list)
    distinct: bool = False
    star: bool = False
    filter_clause: Expr | None = None
    over: 'WindowDef | None' = None


@dataclass
class CaseExpr(Expr):
    base: Expr | None = None
    whens: list[tuple[Expr, Expr]] = field(default_factory=list)
    else_expr: Expr | None = None


@dataclass
class CastExpr(Expr):
    expr: Expr
    type_name: 'TypeName'


@dataclass
class Subquery(Expr):
    select: 'Select'


@dataclass
class ExistsSubquery(Expr):
    select: 'Select'


@dataclass
class InOp(Expr):
    expr: Expr
    values: list[Expr] | None = None
    select: 'Select | None' = None
    table: str | None = None
    negated: bool = False


@dataclass
class BetweenOp(Expr):
    expr: Expr
    low: Expr
    high: Expr
    negated: bool = False


@dataclass
class LikeOp(Expr):
    expr: Expr
    pattern: Expr
    escape: Expr | None = None
    negated: bool = False


@dataclass
class IsOp(Expr):
    left: Expr
    right: Expr
    negated: bool = False


@dataclass
class IsNullOp(Expr):
    expr: Expr
    negated: bool = False


@dataclass
class CollateOp(Expr):
    expr: Expr
    collation: str


@dataclass
class RowValue(Expr):
    values: list[Expr] = field(default_factory=list)


@dataclass
class StarExpr(Expr):
    pass


@dataclass
class RaiseFunction(Expr):
    action: str
    error_msg: str | None = None


# ── Window ──

@dataclass
class WindowDef:
    partition: list[Expr] = field(default_factory=list)
    order: list['OrderingTerm'] = field(default_factory=list)
    frame: 'WindowFrame | None' = None
    name: str | None = None


@dataclass
class WindowFrame:
    unit: str  # ROWS, RANGE, GROUPS
    start: str | None = None
    start_expr: Expr | None = None
    end: str | None = None
    end_expr: Expr | None = None
    exclude: str | None = None


# ── Type / Column / Constraint ──

@dataclass
class TypeName:
    name: str
    precision: int | None = None
    scale: int | None = None


@dataclass
class ColumnConstraint:
    name: str | None = None
    kind: str = ''  # PRIMARY KEY, NOT NULL, UNIQUE, CHECK, DEFAULT, COLLATE, REFERENCES, GENERATED
    details: Any = None


@dataclass
class TableConstraint:
    name: str | None = None
    kind: str = ''
    columns: list[str] = field(default_factory=list)
    expr: Expr | None = None
    details: Any = None


@dataclass
class ColumnDef:
    name: str
    type_name: TypeName | None = None
    constraints: list[ColumnConstraint] = field(default_factory=list)


@dataclass
class ForeignKey:
    table: str
    columns: list[str] = field(default_factory=list)
    parent_columns: list[str] = field(default_factory=list)
    actions: dict[str, str] = field(default_factory=dict)
    match: str | None = None
    deferrable: bool = False
    initially: str | None = None


# ── Table references ──

@dataclass
class TableName:
    name: str
    schema: str | None = None
    alias: str | None = None


@dataclass
class TableFunction:
    name: str
    args: list[Expr] = field(default_factory=list)


@dataclass
class Parameter(Expr):
    name: str  # '?', '?1', ':name', '@name', '$name'


@dataclass
class SubqueryTable:
    select: 'Select'
    alias: str | None = None
    columns: list[str] = field(default_factory=list)


@dataclass
class JoinClause:
    type: str = ''  # '', LEFT, RIGHT, CROSS, NATURAL
    outer: bool = False
    table: Any = None
    on: Expr | None = None
    using: list[str] = field(default_factory=list)


@dataclass
class ResultColumn:
    expr: Expr
    alias: str | None = None


@dataclass
class OrderingTerm:
    expr: Expr
    direction: str = 'ASC'  # ASC, DESC
    nulls: str | None = None  # FIRST, LAST


@dataclass
class SetClause:
    column: str
    expr: Expr


@dataclass
class Returning:
    columns: list[ResultColumn] = field(default_factory=list)


@dataclass
class CTE:
    name: str
    columns: list[str] = field(default_factory=list)
    select: 'Select | None' = None
    recursive: bool = False


# ── DML ──

@dataclass
class Select(Statement):
    columns: list[ResultColumn] = field(default_factory=list)
    distinct: bool = False
    from_clause: list[Any] = field(default_factory=list)  # list of table refs
    where: Expr | None = None
    group_by: list[Expr] = field(default_factory=list)
    having: Expr | None = None
    window: list[tuple[str, WindowDef]] = field(default_factory=list)
    order_by: list[OrderingTerm] = field(default_factory=list)
    limit: Expr | None = None
    offset: Expr | None = None
    ctes: list[CTE] = field(default_factory=list)
    compound_op: str | None = None
    compound_select: 'Select | None' = None
    for_update: bool = False


@dataclass
class Insert(Statement):
    table: TableName
    columns: list[str] = field(default_factory=list)
    values: list[list[Expr]] = field(default_factory=list)
    select: Select | None = None
    default_values: bool = False
    or_action: str | None = None  # ROLLBACK, ABORT, FAIL, IGNORE, REPLACE
    ctes: list[CTE] = field(default_factory=list)
    on_conflict: 'OnConflict | None' = None
    returning: Returning | None = None


@dataclass
class OnConflict:
    columns: list[str] = field(default_factory=list)
    where: Expr | None = None
    action: str = ''  # NOTHING, UPDATE
    set_clauses: list[SetClause] = field(default_factory=list)
    condition: Expr | None = None


@dataclass
class Update(Statement):
    table: TableName
    set_clauses: list[SetClause] = field(default_factory=list)
    from_clause: list[Any] = field(default_factory=list)
    where: Expr | None = None
    order_by: list[OrderingTerm] = field(default_factory=list)
    limit: Expr | None = None
    offset: Expr | None = None
    or_action: str | None = None
    ctes: list[CTE] = field(default_factory=list)
    returning: Returning | None = None


@dataclass
class Delete(Statement):
    table: TableName
    where: Expr | None = None
    order_by: list[OrderingTerm] = field(default_factory=list)
    limit: Expr | None = None
    offset: Expr | None = None
    ctes: list[CTE] = field(default_factory=list)
    returning: Returning | None = None


# ── DDL ──

@dataclass
class CreateTable(Statement):
    name: TableName
    columns: list[ColumnDef] = field(default_factory=list)
    constraints: list[TableConstraint] = field(default_factory=list)
    as_select: Select | None = None
    temp: bool = False
    if_not_exists: bool = False
    without_rowid: bool = False
    strict: bool = False


@dataclass
class CreateIndex(Statement):
    name: str
    table: TableName
    columns: list[OrderingTerm] = field(default_factory=list)
    unique: bool = False
    if_not_exists: bool = False
    where: Expr | None = None
    schema: str | None = None


@dataclass
class CreateView(Statement):
    name: TableName
    select: Select
    temp: bool = False
    if_not_exists: bool = False


@dataclass
class CreateTrigger(Statement):
    name: str
    table: str
    statements: list[Statement] = field(default_factory=list)
    time: str = 'BEFORE'  # BEFORE, AFTER, INSTEAD OF
    event: str = 'INSERT'  # INSERT, UPDATE, DELETE
    columns: list[str] = field(default_factory=list)
    for_each_row: bool = True
    when: Expr | None = None
    schema: str | None = None


@dataclass
class CreateVirtualTable(Statement):
    name: TableName
    module: str
    args: list[str] = field(default_factory=list)
    if_not_exists: bool = False


@dataclass
class DropTable(Statement):
    name: TableName
    if_exists: bool = False


@dataclass
class DropIndex(Statement):
    name: str
    if_exists: bool = False
    schema: str | None = None


@dataclass
class DropView(Statement):
    name: str
    if_exists: bool = False
    schema: str | None = None


@dataclass
class DropTrigger(Statement):
    name: str
    if_exists: bool = False
    schema: str | None = None


@dataclass
class AlterTable(Statement):
    table: TableName
    action: str  # RENAME TO, RENAME COLUMN, ADD COLUMN, DROP COLUMN
    new_name: str | None = None
    column: str | None = None
    new_column: str | None = None
    column_def: ColumnDef | None = None


# ── Transactions ──

@dataclass
class Begin(Statement):
    mode: str | None = None  # DEFERRED, IMMEDIATE, EXCLUSIVE


@dataclass
class Commit(Statement):
    pass


@dataclass
class RollbackStmt(Statement):
    savepoint: str | None = None


@dataclass
class Savepoint(Statement):
    name: str


@dataclass
class Release(Statement):
    savepoint: str


# ── Other ──

@dataclass
class Pragma(Statement):
    name: str
    value: Any = None
    schema: str | None = None


@dataclass
class Analyze(Statement):
    name: str | None = None


@dataclass
class Reindex(Statement):
    name: str | None = None
    schema: str | None = None


@dataclass
class Vacuum(Statement):
    schema: str | None = None


@dataclass
class Explain(Statement):
    statement: Statement
    query_plan: bool = False
