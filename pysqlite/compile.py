"""Bytecode compiler — walks AST and emits VDBE instructions."""

from dataclasses import dataclass, field
from typing import Any

from pysqlite.opcode import Instruction, Opcode
from pysqlite.ast import (
    Statement, Expr,
    Select, Insert, Update, Delete,
    CreateTable, CreateIndex, DropTable, DropIndex,
    CreateView, CreateTrigger, AlterTable,
    Begin, Commit, RollbackStmt, Savepoint, Release,
    Pragma, Explain,
    Literal, NullLiteral, ColumnRef, UnaryOp, BinaryOp,
    FunctionCall, CaseExpr, CastExpr, Subquery, ExistsSubquery,
    InOp, BetweenOp, LikeOp, IsOp, IsNullOp, CollateOp,
    StarExpr, RaiseFunction, RowValue,
    ResultColumn, OrderingTerm, SetClause, Returning, CTE,
    TableName, TableFunction, SubqueryTable, JoinClause,
    ColumnDef, ColumnConstraint, TableConstraint, TypeName,
    WindowDef, WindowFrame, OnConflict,
)


# ── Schema types (will move to schema.py in Phase 5) ──

class AFFINITY:
    INTEGER = 0
    REAL = 1
    NUMERIC = 2
    TEXT = 3
    BLOB = 4


@dataclass
class IndexedColumnDef:
    name: str
    collation: str | None = None
    order: str = 'ASC'
    expr: Expr | None = None


@dataclass
class ColumnDefInfo:
    name: str
    type_name: str | None = None
    affinity: int = AFFINITY.BLOB
    not_null: bool = False
    primary_key: bool = False
    unique: bool = False
    default_value: Any = None
    auto_increment: bool = False
    collation: str | None = None


@dataclass
class IndexDefInfo:
    name: str
    table_name: str
    root_page: int = 0
    columns: list[IndexedColumnDef] = field(default_factory=list)
    unique: bool = False
    partial: bool = False


@dataclass
class TableDefInfo:
    name: str
    root_page: int = 0
    columns: list[ColumnDefInfo] = field(default_factory=list)
    without_rowid: bool = False
    strict: bool = False


# ── Compiler ──

class CompilerError(Exception):
    pass


class Compiler:
    def __init__(self, schema, db=None):
        self.schema = schema
        self.db = db
        self.instructions: list[Instruction] = []
        self.labels: dict[str, int] = {}
        self.pending_labels: dict[str, list[int]] = {}
        self.next_register = 0
        self.next_cursor = 0
        self.loop_break_label: str | None = None

        self.reg_zero = self.alloc_reg()
        self.reg_one = self.alloc_reg()
        self.reg_null = self.alloc_reg()

    # ── Register management ──

    def alloc_reg(self) -> int:
        r = self.next_register
        self.next_register += 1
        return r

    def alloc_regs(self, n: int) -> list[int]:
        regs = list(range(self.next_register, self.next_register + n))
        self.next_register += n
        return regs

    def alloc_cursor(self) -> int:
        c = self.next_cursor
        self.next_cursor += 1
        return c

    # ── Label management ──

    def define_label(self, name: str):
        idx = len(self.instructions)
        self.labels[name] = idx
        if name in self.pending_labels:
            for pos in self.pending_labels.pop(name):
                self.instructions[pos].P2 = idx

    def _label_name(self, prefix: str) -> str:
        n = len(self.labels) + len(self.pending_labels)
        return f'{prefix}_{n}'

    # ── Instruction emission ──

    def emit(self, opcode: str, P1: int = 0, P2: int = 0, P3: int = 0,
             P4: Any = None, P5: int = 0, comment: str = '') -> int:
        idx = len(self.instructions)
        self.instructions.append(Instruction(opcode, P1, P2, P3, P4, P5, comment))
        return idx

    def emit_goto(self, target_label: str):
        idx = self.emit(Opcode.Goto)
        self._patch_jump(idx, target_label)

    def emit_ifnot(self, reg: int, target_label: str):
        idx = self.emit(Opcode.IfNot, P1=reg)
        self._patch_jump(idx, target_label)

    def emit_if(self, reg: int, target_label: str):
        idx = self.emit(Opcode.If, P1=reg)
        self._patch_jump(idx, target_label)

    def emit_isnull(self, reg: int, target_label: str):
        idx = self.emit(Opcode.IsNull, P1=reg)
        self._patch_jump(idx, target_label)

    def emit_notnull(self, reg: int, target_label: str):
        idx = self.emit(Opcode.NotNull, P1=reg)
        self._patch_jump(idx, target_label)

    def emit_compare_branch(self, opcode: str, left: int, right: int, target_label: str):
        idx = self.emit(opcode, P1=left, P3=right)
        self._patch_jump(idx, target_label)

    def _patch_jump(self, instr_idx: int, label: str):
        if label in self.labels:
            self.instructions[instr_idx].P2 = self.labels[label]
        else:
            self.pending_labels.setdefault(label, []).append(instr_idx)

    def init_constants(self):
        self.emit(Opcode.Integer, P1=0, P2=self.reg_zero, comment='constant 0')
        self.emit(Opcode.Integer, P1=1, P2=self.reg_one, comment='constant 1')
        self.emit(Opcode.Null, P1=self.reg_null, comment='constant NULL')

    # ── Main entry point ──

    def compile(self, statement: Statement) -> list[Instruction]:
        self.instructions = []
        self.labels = {}
        self.pending_labels = {}
        self.next_register = 0
        self.next_cursor = 0
        self.reg_zero = self.alloc_reg()
        self.reg_one = self.alloc_reg()
        self.reg_null = self.alloc_reg()

        if isinstance(statement, Select):
            self._compile_select(statement)
        elif isinstance(statement, Insert):
            self._compile_insert(statement)
        elif isinstance(statement, Update):
            self._compile_update(statement)
        elif isinstance(statement, Delete):
            self._compile_delete(statement)
        elif isinstance(statement, CreateTable):
            self._compile_create_table(statement)
        elif isinstance(statement, CreateIndex):
            self._compile_create_index(statement)
        elif isinstance(statement, DropTable):
            self._compile_drop_table(statement)
        elif isinstance(statement, DropIndex):
            self._compile_drop_index(statement)
        elif isinstance(statement, Begin):
            self._compile_begin(statement)
        elif isinstance(statement, Commit):
            self._compile_commit(statement)
        elif isinstance(statement, RollbackStmt):
            self._compile_rollback(statement)
        elif isinstance(statement, Pragma):
            self._compile_pragma(statement)
        elif isinstance(statement, Explain):
            self._compile_explain(statement)
        else:
            raise CompilerError(f'Unsupported statement: {type(statement).__name__}')

        self.emit(Opcode.Halt, comment='end of program')
        self._resolve_labels()
        return self.instructions

    def _resolve_labels(self):
        for label, positions in self.pending_labels.items():
            for pos in positions:
                raise CompilerError(f'Unresolved label: {label}')

    # ── Expression compiler ──

    def compile_expr(self, expr: Expr, cursor: int = 0) -> int:
        reg = self.alloc_reg()
        self._compile_expr_to(expr, reg, cursor)
        return reg

    def _compile_expr_to(self, expr: Expr, reg: int, cursor: int = 0):
        if isinstance(expr, Literal):
            v = expr.value
            if isinstance(v, int):
                self.emit(Opcode.Integer, P1=v, P2=reg, comment=f'const {v}')
            elif isinstance(v, float):
                self.emit(Opcode.Real, P1=v, P2=reg, comment=f'const {v}')
            elif isinstance(v, str):
                self.emit(Opcode.String, P4=v, P2=reg, comment=f'const {v!r}')
            elif isinstance(v, bytes):
                self.emit(Opcode.Blob, P4=v, P2=reg, comment='const blob')
            else:
                self.emit(Opcode.Null, P1=reg, comment=f'const {v!r}')

        elif isinstance(expr, NullLiteral):
            self.emit(Opcode.Null, P1=reg, comment='NULL')

        elif isinstance(expr, ColumnRef):
            table_def = self._lookup_table(cursor)
            col_idx = self._column_index(table_def, expr.name)
            self.emit(Opcode.Column, P1=cursor, P2=col_idx, P3=reg,
                      comment=f'column {expr.name}')

        elif isinstance(expr, UnaryOp):
            operand_reg = self.compile_expr(expr.operand, cursor)
            op = expr.op
            if op == '-':
                self.emit(Opcode.Subtract, P1=self.reg_zero, P3=reg,
                          P4=operand_reg, comment='unary -')
            elif op == '+':
                self.emit(Opcode.MemCopy, P1=operand_reg, P2=reg, comment='unary +')
            elif op == '~':
                self.emit(Opcode.BitNot, P1=operand_reg, P2=reg, comment='unary ~')
            elif op == 'NOT':
                cmp = self.alloc_reg()
                self.emit(Opcode.Integer, P1=0, P2=cmp, comment='false')
                self.emit_compare_branch(Opcode.Eq, operand_reg, cmp, f'_not_true_{id(expr)}')
                self.emit(Opcode.Integer, P1=0, P2=reg, comment='NOT -> false')
                goto_idx = self.emit(Opcode.Goto, comment='skip true')
                self.define_label(f'_not_true_{id(expr)}')
                self.emit(Opcode.Integer, P1=1, P2=reg, comment='NOT -> true')
                self.instructions[goto_idx].P2 = len(self.instructions)

        elif isinstance(expr, BinaryOp):
            self._compile_binary_op(expr, reg, cursor)

        elif isinstance(expr, FunctionCall):
            arg_regs = [self.compile_expr(a, cursor) for a in expr.args]
            first_reg = arg_regs[0] if arg_regs else 0
            n_args = len(arg_regs)
            if expr.name.upper() == 'LIKE':
                self.emit(Opcode.Like, P1=first_reg, P3=reg,
                          P4=n_args, comment='LIKE')
            elif expr.name.upper() == 'GLOB':
                self.emit(Opcode.Glob, P1=first_reg, P3=reg,
                          P4=n_args, comment='GLOB')
            elif expr.star:
                self.emit(Opcode.Count, P1=reg, comment='COUNT(*)')
            else:
                self.emit(Opcode.Function, P1=first_reg, P2=n_args, P3=reg,
                          P4=expr.name, comment=f'func {expr.name}')

        elif isinstance(expr, CaseExpr):
            end_label = self._label_name('case_end')
            if expr.base:
                base_reg = self.compile_expr(expr.base, cursor)
            else:
                base_reg = None
            next_label = None
            for when_expr, then_expr in expr.whens:
                if next_label is not None:
                    self.define_label(next_label)
                next_label = self._label_name('case_when')
                when_reg = self.compile_expr(when_expr, cursor)
                if base_reg is not None:
                    cmp_reg = self.alloc_reg()
                    self.emit(Opcode.Eq, P1=base_reg, P2=cmp_reg, P3=when_reg,
                              comment='CASE equality')
                    self.emit_ifnot(cmp_reg, next_label)
                else:
                    self.emit_ifnot(when_reg, next_label)
                self._compile_expr_to(then_expr, reg, cursor)
                self.emit_goto(end_label)
            if next_label is not None:
                self.define_label(next_label)
            if expr.else_expr:
                self._compile_expr_to(expr.else_expr, reg, cursor)
            else:
                self.emit(Opcode.Null, P1=reg, comment='CASE else NULL')
            self.define_label(end_label)

        elif isinstance(expr, CastExpr):
            inner_reg = self.compile_expr(expr.expr, cursor)
            self.emit(Opcode.Cast, P1=inner_reg, P2=reg,
                      P4=expr.type_name.name.upper(), comment=f'CAST to {expr.type_name.name}')

        elif isinstance(expr, IsNullOp):
            self.emit(Opcode.Null, P1=reg, comment='temp')
            op = Opcode.Eq if expr.negated else Opcode.Ne
            self.emit_compare_branch(op, self.compile_expr(expr.expr, cursor), self.reg_null, f'_isnull_{id(expr)}')
            self.emit(Opcode.Integer, P1=1 if expr.negated else 0, P2=reg)

        elif isinstance(expr, BetweenOp):
            lo_reg = self.compile_expr(expr.low, cursor)
            hi_reg = self.compile_expr(expr.high, cursor)
            inner = self.compile_expr(expr.expr, cursor)
            ge_reg = self.alloc_reg()
            le_reg = self.alloc_reg()
            self.emit(Opcode.Ge, P1=inner, P2=ge_reg, P3=lo_reg, comment='BETWEEN low')
            self.emit(Opcode.Le, P1=inner, P2=le_reg, P3=hi_reg, comment='BETWEEN high')
            if expr.negated:
                self.emit(Opcode.And, P1=ge_reg, P2=le_reg, P3=reg)
                self.emit(Opcode.Not, P1=reg, P2=reg)
            else:
                self.emit(Opcode.And, P1=ge_reg, P2=le_reg, P3=reg)

        elif isinstance(expr, LikeOp):
            left = self.compile_expr(expr.expr, cursor)
            right = self.compile_expr(expr.pattern, cursor)
            self.emit(Opcode.Like, P1=left, P3=reg, P4=1, comment='LIKE')
            if expr.negated:
                self.emit(Opcode.Not, P1=reg, P2=reg)

        elif isinstance(expr, InOp):
            inner = self.compile_expr(expr.expr, cursor)
            target = self._label_name('in_found')
            end = self._label_name('in_end')
            if expr.values:
                for v in expr.values:
                    vr = self.compile_expr(v, cursor)
                    self.emit_compare_branch(Opcode.Eq, inner, vr, target)
            elif expr.select:
                sub_reg = self.compile_expr(expr.select, cursor)
                self.emit_compare_branch(Opcode.Eq, inner, sub_reg, target)
            self.emit(Opcode.Integer, P1=0 if not expr.negated else 1, P2=reg)
            self.emit_goto(end)
            self.define_label(target)
            self.emit(Opcode.Integer, P1=1 if not expr.negated else 0, P2=reg)
            self.define_label(end)

        elif isinstance(expr, IsOp):
            left = self.compile_expr(expr.left, cursor)
            right = self.compile_expr(expr.right, cursor)
            op = Opcode.Ne if expr.negated else Opcode.Eq
            self.emit_compare_branch(op, left, right, f'_is_{id(expr)}')
            self.emit(Opcode.Integer, P1=1 if not expr.negated else 0, P2=reg)

        elif isinstance(expr, Subquery):
            sub_compiler = Compiler(self.schema, self.db)
            sub_prog = sub_compiler.compile(expr.select)
            self.instructions.extend(sub_prog)
            # subquery result should be in a known register
            for instr in sub_prog:
                if instr.opcode == Opcode.ResultRow:
                    self.emit(Opcode.MemCopy, P1=instr.P1, P2=reg,
                              comment='subquery result')

        elif isinstance(expr, CollateOp):
            inner = self.compile_expr(expr.expr, cursor)
            self.emit(Opcode.MemCopy, P1=inner, P2=reg, comment='COLLATE (passthrough)')

        elif isinstance(expr, StarExpr):
            self.emit(Opcode.Null, P1=reg, comment='STAR expression')

        else:
            raise CompilerError(f'Unsupported expression: {type(expr).__name__}')

    # ── Binary operator compilation ──

    _ARITH_OP_MAP = {
        '+': Opcode.Add, '-': Opcode.Subtract, '*': Opcode.Multiply,
        '/': Opcode.Divide, '%': Opcode.Remainder, '||': Opcode.Concat,
        '&': Opcode.BitAnd, '|': Opcode.BitOr,
        '<<': Opcode.ShiftLeft, '>>': Opcode.ShiftRight,
    }

    _CMP_OP_MAP = {
        '=': Opcode.Eq, '==': Opcode.Eq, '<>': Opcode.Ne, '!=': Opcode.Ne,
        '<': Opcode.Lt, '<=': Opcode.Le, '>': Opcode.Gt, '>=': Opcode.Ge,
    }

    def _compile_binary_op(self, expr: BinaryOp, reg: int, cursor: int):
        op = expr.op
        if op == 'AND':
            end_label = self._label_name('and_end')
            false_label = self._label_name('and_false')
            left_reg = self.compile_expr(expr.left, cursor)
            self.emit_ifnot(left_reg, false_label)
            right_reg = self.compile_expr(expr.right, cursor)
            self.emit(Opcode.MemCopy, P1=right_reg, P2=reg, comment='AND result')
            self.emit_goto(end_label)
            self.define_label(false_label)
            self.emit(Opcode.Integer, P1=0, P2=reg, comment='AND false')
            self.define_label(end_label)
        elif op == 'OR':
            end_label = self._label_name('or_end')
            true_label = self._label_name('or_true')
            left_reg = self.compile_expr(expr.left, cursor)
            self.emit_if(left_reg, true_label)
            right_reg = self.compile_expr(expr.right, cursor)
            self.emit(Opcode.MemCopy, P1=right_reg, P2=reg, comment='OR result')
            self.emit_goto(end_label)
            self.define_label(true_label)
            self.emit(Opcode.Integer, P1=1, P2=reg, comment='OR true')
            self.define_label(end_label)
        elif op in self._ARITH_OP_MAP:
            vop = self._ARITH_OP_MAP[op]
            left_reg = self.compile_expr(expr.left, cursor)
            right_reg = self.compile_expr(expr.right, cursor)
            self.emit(vop, P1=left_reg, P2=reg, P3=right_reg, comment=f'arithmetic {op}')
        elif op in self._CMP_OP_MAP:
            vop = self._CMP_OP_MAP[op]
            left_reg = self.compile_expr(expr.left, cursor)
            right_reg = self.compile_expr(expr.right, cursor)
            true_label = self._label_name('cmp_true')
            end_label = self._label_name('cmp_end')
            self.emit(vop, P1=left_reg, P2=0, P3=right_reg, comment=f'compare {op}')
            # At this point, if comparison is false, we fall through; if true, we jump
            # Actually we emit the compare-and-branch:
            idx = self.emit(vop, P1=left_reg, P2=0, P3=right_reg, comment=f'{op}')
            self._patch_jump(idx, true_label)
            self.emit(Opcode.Integer, P1=0, P2=reg, comment=f'{op} false')
            self.emit_goto(end_label)
            self.define_label(true_label)
            self.emit(Opcode.Integer, P1=1, P2=reg, comment=f'{op} true')
            self.define_label(end_label)
        else:
            raise CompilerError(f'Unsupported binary operator: {op}')

    # ── SELECT ──

    def _compile_select(self, node: Select):
        if node.ctes:
            self._compile_cte(node.ctes)
        cursor = self.alloc_cursor()
        # Determine table/root page
        if node.from_clause:
            table_ref = node.from_clause[0]
            if isinstance(table_ref, TableName):
                td = self._lookup_table_def(table_ref.name, table_ref.schema)
                self.emit(Opcode.Transaction, P1=0, comment='begin read')
                self.emit(Opcode.OpenRead, P1=cursor, P2=td.root_page,
                          P3=len(td.columns), comment=f'open {td.name}')
                self.emit(Opcode.Rewind, P1=cursor, P2=len(self.instructions) + 4,
                          comment='rewind')
            elif isinstance(table_ref, SubqueryTable):
                sub = Compiler(self.schema, self.db)
                sub_prog = sub.compile(table_ref.select)
                self.instructions.extend(sub_prog)
                self.emit(Opcode.OpenEphemeral, P1=cursor, P2=1,
                          comment='subquery result')
            else:
                self.emit(Opcode.OpenEphemeral, P1=cursor, P2=1,
                          comment='table ref')
        else:
            # No FROM clause (e.g., SELECT 1)
            self.emit(Opcode.OpenEphemeral, P1=cursor, P2=1,
                      comment='dummy scan')

        # WHERE clause
        loop_start = len(self.instructions)
        if node.from_clause:
            pass  # Rewind already positions cursor, Next handles loop

        where_skip = None
        if node.where:
            where_reg = self.compile_expr(node.where, cursor)
            where_skip = self._label_name('where_skip')
            self.emit_ifnot(where_reg, where_skip)

        # Result columns
        col_regs = []
        for rc in node.columns:
            if isinstance(rc.expr, StarExpr):
                td = self._lookup_table(cursor)
                for i in range(len(getattr(td, 'columns', []))):
                    r = self.alloc_reg()
                    col_regs.append(r)
                    self.emit(Opcode.Column, P1=cursor, P2=i, P3=r,
                              comment=f'column {i}')
            else:
                r = self.compile_expr(rc.expr, cursor)
                col_regs.append(r)

        if col_regs:
            first_reg = min(col_regs)
            n_cols = len(col_regs)
        else:
            first_reg = 0
            n_cols = 0

        self.emit(Opcode.ResultRow, P1=first_reg, P2=n_cols, comment='emit row')

        if where_skip:
            self.define_label(where_skip)

        # ORDER BY
        if node.order_by:
            self._compile_order_by(cursor, node.order_by)

        # LIMIT / OFFSET
        if node.limit or node.offset:
            if node.limit:
                limit_reg = self.compile_expr(node.limit, cursor)
            else:
                limit_reg = self.reg_null
            if node.offset:
                offset_reg = self.compile_expr(node.offset, cursor)
                self.emit(Opcode.IfNotZero, P1=offset_reg, P2=0, P3=1,
                          comment='skip offset')

        # Loop
        if node.from_clause:
            self.emit(Opcode.Next, P1=cursor, P2=loop_start, comment='next row')

        # Compound (UNION/INTERSECT/EXCEPT)
        if node.compound_select:
            self._compile_compound(node)

    def _compile_compound(self, node: Select):
        ep = self.alloc_cursor()
        self.emit(Opcode.OpenEphemeral, P1=ep, P2=1, comment='compound set')
        op = node.compound_op.upper() if node.compound_op else 'UNION'

    def _compile_order_by(self, cursor: int, terms: list[OrderingTerm]):
        pass  # In-memory sort — add sorter logic when needed

    # ── INSERT ──

    def _compile_insert(self, node: Insert):
        if node.ctes:
            self._compile_cte(node.ctes)
        td = self._lookup_table_def(node.table.name, node.table.schema)
        cursor = self.alloc_cursor()
        self.emit(Opcode.Transaction, P1=1, comment='begin write')
        self.emit(Opcode.OpenWrite, P1=cursor, P2=td.root_page,
                  P3=len(td.columns), comment=f'open {td.name}')

        if node.default_values:
            rowid_reg = self.alloc_reg()
            self.emit(Opcode.NewRowid, P1=cursor, P2=0, P3=rowid_reg,
                      comment='new rowid')
            record_reg = self.alloc_reg()
            self.emit(Opcode.MakeRecord, P1=self.reg_null, P2=1, P3=record_reg,
                      comment='default values record')
            self.emit(Opcode.Insert, P1=cursor, P2=record_reg, P3=rowid_reg,
                      comment='insert row')
        elif node.select:
            self._compile_select(node.select)
        elif node.values:
            col_count = len(td.columns) if not node.columns else len(node.columns)
            for row in node.values:
                val_regs = []
                for val in row:
                    vr = self.compile_expr(val, 0)
                    val_regs.append(vr)
                rowid_reg = self.alloc_reg()
                self.emit(Opcode.NewRowid, P1=cursor, P2=0, P3=rowid_reg,
                          comment='new rowid')
                first_val = val_regs[0] if val_regs else self.reg_null
                record_reg = self.alloc_reg()
                self.emit(Opcode.MakeRecord, P1=first_val, P2=len(val_regs),
                          P3=record_reg, comment='make record')
                self.emit(Opcode.Insert, P1=cursor, P2=record_reg, P3=rowid_reg,
                          comment='insert row')
        if node.returning:
            self._compile_returning(cursor, node.returning)

    # ── UPDATE ──

    def _compile_update(self, node: Update):
        if node.ctes:
            self._compile_cte(node.ctes)
        td = self._lookup_table_def(node.table.name, node.table.schema)
        cursor = self.alloc_cursor()
        self.emit(Opcode.Transaction, P1=1, comment='begin write')
        self.emit(Opcode.OpenWrite, P1=cursor, P2=td.root_page,
                  P3=len(td.columns), comment=f'open {td.name}')
        self.emit(Opcode.Rewind, P1=cursor, P2=0, comment='rewind')

        loop_start = len(self.instructions)
        if node.where:
            where_reg = self.compile_expr(node.where, cursor)
            skip_label = self._label_name('update_skip')
            self.emit_ifnot(where_reg, skip_label)

        # Delete old index entries, then update row
        rowid_reg = self.alloc_reg()
        self.emit(Opcode.Rowid, P1=cursor, P2=rowid_reg, comment='current rowid')
        col_regs = []
        for sc in node.set_clauses:
            vr = self.compile_expr(sc.expr, cursor)
            col_regs.append(vr)
        self.emit(Opcode.Delete, P1=cursor, comment='delete old row')

        # Insert updated row
        first_val = col_regs[0] if col_regs else self.reg_null
        record_reg = self.alloc_reg()
        self.emit(Opcode.MakeRecord, P1=first_val, P2=len(col_regs),
                  P3=record_reg, comment='update record')
        self.emit(Opcode.Insert, P1=cursor, P2=record_reg, P3=rowid_reg,
                  comment='insert updated row')

        if node.where:
            self.define_label(skip_label)
        self.emit(Opcode.Next, P1=cursor, P2=loop_start, comment='next row')
        if node.returning:
            self._compile_returning(cursor, node.returning)

    # ── DELETE ──

    def _compile_delete(self, node: Delete):
        if node.ctes:
            self._compile_cte(node.ctes)
        td = self._lookup_table_def(node.table.name, node.table.schema)
        cursor = self.alloc_cursor()
        self.emit(Opcode.Transaction, P1=1, comment='begin write')
        self.emit(Opcode.OpenWrite, P1=cursor, P2=td.root_page,
                  P3=len(td.columns), comment=f'open {td.name}')
        self.emit(Opcode.Rewind, P1=cursor, P2=0, comment='rewind')
        loop_start = len(self.instructions)

        if node.where:
            where_reg = self.compile_expr(node.where, cursor)
            skip_label = self._label_name('delete_skip')
            self.emit_ifnot(where_reg, skip_label)

        self.emit(Opcode.Delete, P1=cursor, comment='delete row')
        if node.where:
            self.define_label(skip_label)
        self.emit(Opcode.Next, P1=cursor, P2=loop_start, comment='next row')
        if node.returning:
            self._compile_returning(cursor, node.returning)

    # ── DDL ──

    def _compile_create_table(self, node: CreateTable):
        self.emit(Opcode.Transaction, P1=1, comment='DDL begin write')
        self.emit(Opcode.CreateTable, P1=0, P4=node.name.name,
                  comment=f'CREATE TABLE {node.name.name}')

    def _compile_create_index(self, node: CreateIndex):
        self.emit(Opcode.Transaction, P1=1, comment='DDL begin write')
        self.emit(Opcode.CreateIndex, P1=0, P4=node.name,
                  comment=f'CREATE INDEX {node.name}')

    def _compile_drop_table(self, node: DropTable):
        self.emit(Opcode.Transaction, P1=1, comment='DDL begin write')
        self.emit(Opcode.DropTable, P1=0, P4=node.name.name,
                  comment=f'DROP TABLE {node.name.name}')

    def _compile_drop_index(self, node: DropIndex):
        self.emit(Opcode.Transaction, P1=1, comment='DDL begin write')
        self.emit(Opcode.DropIndex, P1=0, P4=node.name,
                  comment=f'DROP INDEX {node.name}')

    # ── Transactions ──

    def _compile_begin(self, node: Begin):
        self.emit(Opcode.Transaction, P1=1, comment='BEGIN')

    def _compile_commit(self, node: Commit):
        self.emit(Opcode.Transaction, P1=0, comment='COMMIT')

    def _compile_rollback(self, node: RollbackStmt):
        self.emit(Opcode.Transaction, P1=-1, comment='ROLLBACK')

    # ── PRAGMA ──

    def _compile_pragma(self, node: Pragma):
        reg = self.alloc_reg()
        self.emit(Opcode.String, P4=str(node.value) if node.value is not None else '',
                  P2=reg, comment=f'PRAGMA {node.name}')
        self.emit(Opcode.ResultRow, P1=reg, P2=1, comment='pragma result')

    # ── EXPLAIN ──

    def _compile_explain(self, node: Explain):
        stmt = node.statement
        inner = self.compile(stmt)
        self.instructions = [
            Instruction(Opcode.Explain, comment='EXPLAIN')
        ] + inner

    # ── RETURNING ──

    def _compile_returning(self, cursor: int, ret: Returning):
        for rc in ret.columns:
            reg = self.compile_expr(rc.expr, cursor)
            self.emit(Opcode.ResultColumn, P1=reg, comment='RETURNING')

    # ── CTE ──

    def _compile_cte(self, ctes: list[CTE]):
        pass  # Placeholder — will implement when needed

    # ── Schema lookups ──

    def _lookup_table(self, cursor: int) -> TableDefInfo | None:
        return None

    def _lookup_table_def(self, name: str, schema: str | None = None) -> TableDefInfo:
        if self.schema is not None and hasattr(self.schema, 'get_table'):
            td = self.schema.get_table(name, schema)
            if td is not None:
                return td
        return TableDefInfo(name=name, root_page=1, columns=[])

    def _column_index(self, table_def: TableDefInfo | None, col_name: str) -> int:
        if table_def and table_def.columns:
            for i, c in enumerate(table_def.columns):
                if c.name.upper() == col_name.upper():
                    return i
        return 0
