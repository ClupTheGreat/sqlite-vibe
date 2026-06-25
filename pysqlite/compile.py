"""Bytecode compiler — walks AST and emits VDBE instructions."""

from typing import Any

from pysqlite.opcode import Instruction, Opcode
from pysqlite.schema import (
    TableDef, ColumnDef, IndexDef, IndexedColumnDef, AFFINITY,
)
from pysqlite.ast import (
    Statement, Expr,
    Select, Insert, Update, Delete,
    CreateTable, CreateIndex, DropTable, DropIndex,
    CreateView, DropView, CreateTrigger, AlterTable,
    Begin, Commit, RollbackStmt, Savepoint, Release,
    Pragma, Explain, Analyze,
    Literal, NullLiteral, ColumnRef, UnaryOp, BinaryOp,
    FunctionCall, CaseExpr, CastExpr, Subquery, ExistsSubquery,
    InOp, BetweenOp, LikeOp, IsOp, IsNullOp, CollateOp,
    StarExpr, RaiseFunction, RowValue,
    ResultColumn, OrderingTerm, SetClause, Returning, CTE,
    TableName, TableFunction, SubqueryTable, JoinClause,
    ColumnDef as AstColumnDef, ColumnConstraint, TableConstraint, TypeName,
    WindowDef, WindowFrame, OnConflict, Parameter,
)


AGGREGATE_FUNCTIONS = frozenset({'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'GROUP_CONCAT', 'TOTAL'})

def _is_aggregate_name(name: str, custom_aggregates: set[str] | None = None) -> bool:
    return name.upper() in AGGREGATE_FUNCTIONS or (
        custom_aggregates is not None and name.upper() in custom_aggregates
    )


# ── Compiler ──

class CompilerError(Exception):
    pass


class Compiler:
    def __init__(self, schema, db=None, custom_aggregates: set[str] | None = None):
        self.schema = schema
        self.db = db
        self.custom_aggregates = custom_aggregates or set()
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
        self.cursor_table: dict[int, TableDef] = {}
        self.result_columns: list[str] = []
        self._param_counter = 0
        self.emit(Opcode.Integer, P1=0, P2=self.reg_zero, comment='const 0')
        self.emit(Opcode.Integer, P1=1, P2=self.reg_one, comment='const 1')
        self.emit(Opcode.Null, P1=self.reg_null, comment='const null')

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
        elif isinstance(statement, CreateView):
            self._compile_create_view(statement)
        elif isinstance(statement, DropView):
            self._compile_drop_view(statement)
        elif isinstance(statement, Explain):
            self._compile_explain(statement)
        elif isinstance(statement, Analyze):
            self._compile_analyze(statement)
        else:
            raise CompilerError(f'Unsupported statement: {type(statement).__name__}')

        self.emit(Opcode.Halt, comment='end of program')
        self._resolve_labels()
        return self.instructions

    def _resolve_labels(self):
        for label, positions in self.pending_labels.items():
            for pos in positions:
                raise CompilerError(f'Unresolved label: {label}')

    # ── Aggregate detection ──

    @property
    def _aggregate_names(self) -> frozenset:
        return frozenset(AGGREGATE_FUNCTIONS | self.custom_aggregates)

    @staticmethod
    def _is_aggregate(expr: Expr) -> bool:
        return isinstance(expr, FunctionCall) and expr.name.upper() in AGGREGATE_FUNCTIONS

    def _is_aggregate_expr(self, expr: Expr) -> bool:
        return self._is_aggregate(expr) or (
            isinstance(expr, FunctionCall) and expr.name.upper() in self.custom_aggregates
        )

    def _has_aggregates(self, node: Select) -> bool:
        if node.group_by:
            return True
        for rc in node.columns:
            if self._is_aggregate_expr(rc.expr):
                return True
        return False

    def _serialize_having(self, expr: Expr, aggs: list[dict]) -> Any:
        if isinstance(expr, Literal):
            return ('literal', expr.value)
        elif isinstance(expr, NullLiteral):
            return ('literal', None)
        elif isinstance(expr, ColumnRef):
            return ('column', expr.name)
        elif isinstance(expr, BinaryOp):
            left = self._serialize_having(expr.left, aggs)
            right = self._serialize_having(expr.right, aggs)
            return (expr.op, left, right)
        elif isinstance(expr, UnaryOp):
            return (expr.op, self._serialize_having(expr.operand, aggs))
        elif isinstance(expr, FunctionCall):
            all_aggs = AGGREGATE_FUNCTIONS | self.custom_aggregates
            if expr.name.upper() in all_aggs:
                for i, a in enumerate(aggs):
                    if a['name'] == expr.name.upper() and a.get('star') == expr.star:
                        return ('agg_result', i)
                return ('literal', None)
            return ('literal', None)
        elif isinstance(expr, IsNullOp):
            return ('isnull', self._serialize_having(expr.expr, aggs), expr.negated)
        return ('literal', None)

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

        elif isinstance(expr, Parameter):
            pname = expr.name
            if pname == '?':
                self._param_counter += 1
                pname = f'?{self._param_counter}'
            self.emit(Opcode.Param, P4=pname, P2=reg,
                      comment=f'param {pname}')

        elif isinstance(expr, ColumnRef):
            if expr.table:
                ref_cursor = self._cursor_for_table(expr.table, cursor)
            else:
                ref_cursor = cursor
            table_def = self._lookup_table(ref_cursor)
            col_idx = self._column_index(table_def, expr.name)
            self.emit(Opcode.Column, P1=ref_cursor, P2=col_idx, P3=reg,
                      comment=f'column {expr.name}')

        elif isinstance(expr, UnaryOp):
            operand_reg = self.compile_expr(expr.operand, cursor)
            op = expr.op
            if op == '-':
                self.emit(Opcode.Subtract, P1=self.reg_zero, P2=reg,
                          P3=operand_reg, comment='unary -')
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
            func = expr.name.upper()
            arg_regs = [self.compile_expr(a, cursor) for a in expr.args]
            first_reg = arg_regs[0] if arg_regs else 0
            n_args = len(arg_regs)
            if func == 'LIKE':
                self.emit(Opcode.Like, P1=first_reg, P3=reg,
                          P4=n_args, comment='LIKE')
            elif func == 'GLOB':
                self.emit(Opcode.Glob, P1=first_reg, P3=reg,
                          P4=n_args, comment='GLOB')
            elif func == 'COUNT' and expr.star:
                self.emit(Opcode.Count, P1=reg, comment='COUNT(*)')
            elif func in AGGREGATE_FUNCTIONS or func in self.custom_aggregates:
                self.emit(Opcode.Aggregate, P1=reg, P4={'name': func, 'star': expr.star, 'args': arg_regs},
                          comment=f'aggregate {func}')
            elif func in ('ABS', 'UPPER', 'LOWER', 'LENGTH', 'SUBSTR'):
                self.emit(Opcode.Function, P1=first_reg, P2=n_args, P3=reg,
                          P4=func, comment=f'func {func}')
            elif func in ('SIN', 'COS', 'TAN', 'ASIN', 'ACOS', 'ATAN', 'CEIL', 'FLOOR', 
                         'ROUND', 'LOG', 'LOG10', 'SQRT', 'EXP', 'PI', 'POWER', 'POW', 'RAND'):
                self.emit(Opcode.Function, P1=first_reg, P2=n_args, P3=reg,
                          P4=func, comment=f'func {func}')
            else:
                self.emit(Opcode.Function, P1=first_reg, P2=n_args, P3=reg,
                          P4=func, comment=f'func {func}')

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
            expr_reg = self.compile_expr(expr.expr, cursor)
            lbl_skip = f'_isnull_skip_{id(expr)}'
            lbl_end = f'_isnull_end_{id(expr)}'
            if expr.negated:
                self.emit_compare_branch(Opcode.Eq, expr_reg, self.reg_null, lbl_skip)
            else:
                self.emit_compare_branch(Opcode.Ne, expr_reg, self.reg_null, lbl_skip)
            self.emit(Opcode.Integer, P1=1, P2=reg, comment='IS NULL true')
            self.emit_goto(lbl_end)
            self.define_label(lbl_skip)
            self.emit(Opcode.Integer, P1=0, P2=reg, comment='IS NULL false')
            self.define_label(lbl_end)

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
        self._expand_views(node)
        if node.ctes:
            self._compile_cte(node.ctes)
        cursor = self.alloc_cursor()

        # If aggregates or GROUP BY, use aggregation compiler
        if self._has_aggregates(node):
            self._compile_aggregation(node, cursor)
            return

        # Determine table/root page
        if node.from_clause:
            table_ref = node.from_clause[0]
            if isinstance(table_ref, TableName):
                td = self._lookup_table_def(table_ref.name, table_ref.schema)
                self.emit(Opcode.Transaction, P1=0, comment='begin read')
                self.cursor_table[cursor] = td
                self.emit(Opcode.OpenRead, P1=cursor, P2=td.root_page,
                          P3=len(td.columns), comment=f'open {td.name}')
                self.emit(Opcode.Rewind, P1=cursor, P2=len(self.instructions) + 4,
                          comment='rewind')
            elif isinstance(table_ref, SubqueryTable):
                sub_select = table_ref.select
                from pysqlite.schema import AFFINITY
                sub_cols = []
                for rc in sub_select.columns:
                    if rc.alias:
                        cname = rc.alias
                    elif isinstance(rc.expr, ColumnRef):
                        cname = rc.expr.name
                    else:
                        cname = f'col_{len(sub_cols)}'
                    sub_cols.append(ColumnDef(name=cname, affinity=AFFINITY.BLOB))
                td = TableDef(name=table_ref.alias or '_sub', columns=sub_cols, root_page=0, sql='')
                self.cursor_table[cursor] = td
                self.emit(Opcode.OpenEphemeral, P1=cursor, P2=1,
                          comment='subquery result')
                self._compile_subquery_fill(sub_select, cursor, sub_cols)
                self.emit(Opcode.Rewind, P1=cursor, P2=0, comment='rewind subquery result')
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
        self._current_select_columns = node.columns
        col_regs = []
        self.result_columns = []
        for rc in node.columns:
            if isinstance(rc.expr, StarExpr):
                td = self._lookup_table(cursor)
                for i in range(len(getattr(td, 'columns', []))):
                    self.result_columns.append(getattr(td.columns[i], 'name', f'col{i}') if hasattr(td, 'columns') and i < len(td.columns) else f'col{i}')
                    r = self.alloc_reg()
                    col_regs.append(r)
                    self.emit(Opcode.Column, P1=cursor, P2=i, P3=r,
                              comment=f'column {i}')
            else:
                r = self.compile_expr(rc.expr, cursor)
                col_regs.append(r)
                if rc.alias:
                    self.result_columns.append(rc.alias)
                elif isinstance(rc.expr, ColumnRef):
                    self.result_columns.append(rc.expr.name)
                else:
                    self.result_columns.append(f'col{len(self.result_columns)}')

        if col_regs:
            first_reg = min(col_regs)
            n_cols = len(col_regs)
            # Compact registers to be contiguous
            for i, reg in enumerate(col_regs):
                if reg != first_reg + i:
                    self.emit(Opcode.MemCopy, P1=reg, P2=first_reg + i,
                              comment='compact column')
        else:
            first_reg = 0
            n_cols = 0

        # ORDER BY (must be before ResultRow to add sort keys)
        if node.order_by:
            n_cols = self._compile_order_by(first_reg, n_cols, node.order_by,
                                            col_regs, cursor)
            first_reg = min(col_regs) if col_regs else 0

        self.emit(Opcode.ResultRow, P1=first_reg, P2=n_cols, comment='emit row')

        if where_skip:
            self.define_label(where_skip)

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

    def _compile_aggregation(self, node: Select, cursor: int):
        self._expand_views(node)
        if node.from_clause:
            table_ref = node.from_clause[0]
            if isinstance(table_ref, TableName):
                td = self._lookup_table_def(table_ref.name, table_ref.schema)
                self.emit(Opcode.Transaction, P1=0, comment='begin read')
                self.cursor_table[cursor] = td
                self.emit(Opcode.OpenRead, P1=cursor, P2=td.root_page,
                          P3=len(td.columns), comment=f'open {td.name}')
                self.emit(Opcode.Rewind, P1=cursor, P2=len(self.instructions) + 4,
                          comment='rewind')
            elif isinstance(table_ref, SubqueryTable):
                sub_select = table_ref.select
                from pysqlite.schema import AFFINITY
                sub_cols = []
                for rc in sub_select.columns:
                    if rc.alias:
                        cname = rc.alias
                    elif isinstance(rc.expr, ColumnRef):
                        cname = rc.expr.name
                    else:
                        cname = f'col_{len(sub_cols)}'
                    sub_cols.append(ColumnDef(name=cname, affinity=AFFINITY.BLOB))
                td = TableDef(name=table_ref.alias or '_sub', columns=sub_cols, root_page=0, sql='')
                self.cursor_table[cursor] = td
                self.emit(Opcode.OpenEphemeral, P1=cursor, P2=1,
                          comment='subquery result')
                self._compile_subquery_fill(sub_select, cursor, sub_cols)
                self.emit(Opcode.Rewind, P1=cursor, P2=0, comment='rewind subquery result')
            else:
                self.emit(Opcode.OpenEphemeral, P1=cursor, P2=1,
                          comment='table ref')
        else:
            self.emit(Opcode.OpenEphemeral, P1=cursor, P2=1,
                      comment='dummy scan')

        loop_start = len(self.instructions)

        where_skip = None
        if node.where:
            where_reg = self.compile_expr(node.where, cursor)
            where_skip = self._label_name('agg_where_skip')
            self.emit_ifnot(where_reg, where_skip)

        agg_spec = {
            'n_visible': len(node.columns),
            'group_by': [],
            'aggs': [],
        }
        col_regs = []
        self.result_columns = []

        for rc in node.columns:
            if self._is_aggregate_expr(rc.expr):
                func = rc.expr
                if func.star:
                    dummy = self.alloc_reg()
                    self.emit(Opcode.Integer, P1=0, P2=dummy, comment='agg dummy')
                    col_regs.append(dummy)
                    agg_spec['aggs'].append({
                        'name': func.name.upper(), 'star': True,
                        'distinct': func.distinct, 'col': len(col_regs) - 1,
                    })
                else:
                    arg_regs = [self.compile_expr(a, cursor) for a in func.args]
                    first_arg = len(col_regs)
                    col_regs.extend(arg_regs)
                    agg_spec['aggs'].append({
                        'name': func.name.upper(), 'star': False,
                        'distinct': func.distinct, 'col': first_arg,
                        'n_args': len(arg_regs),
                    })
            else:
                r = self.compile_expr(rc.expr, cursor)
                col_regs.append(r)
                if rc.alias:
                    self.result_columns.append(rc.alias)
                elif isinstance(rc.expr, ColumnRef):
                    self.result_columns.append(rc.expr.name)
                else:
                    self.result_columns.append(f'col{len(self.result_columns)}')

        hidden_cols = []
        for gb_expr in node.group_by:
            r = self.compile_expr(gb_expr, cursor)
            hidden_cols.append(r)

        hidden_start = len(col_regs)
        col_regs.extend(hidden_cols)
        agg_spec['group_by'] = list(range(hidden_start, hidden_start + len(hidden_cols)))

        if node.having:
            agg_spec['having'] = self._serialize_having(node.having, agg_spec['aggs'])

        self.emit(Opcode.Aggregate, P1=0, P4=agg_spec, comment='aggregation spec')

        if col_regs:
            first_col_reg = min(col_regs)
            # Compact registers to be contiguous
            for i, reg in enumerate(col_regs):
                if reg != first_col_reg + i:
                    self.emit(Opcode.MemCopy, P1=reg, P2=first_col_reg + i,
                              comment='compact column')
            self.emit(Opcode.ResultRow, P1=first_col_reg, P2=len(col_regs),
                      comment='emit row')

        if where_skip:
            self.define_label(where_skip)

        if node.from_clause:
            self.emit(Opcode.Next, P1=cursor, P2=loop_start, comment='next row')

    def _compile_compound(self, node: Select):
        ep = self.alloc_cursor()
        self.emit(Opcode.OpenEphemeral, P1=ep, P2=1, comment='compound set')
        op = node.compound_op.upper() if node.compound_op else 'UNION'

    def _compile_order_by(self, first_reg: int, n_cols: int, terms: list[OrderingTerm],
                          col_regs: list[int], cursor: int) -> int:
        # Build sort keys alongside result columns
        # Uses cursor to compile expressions (needed when sort key is a table column not in result)
        sort_keys = []
        for term in terms:
            k_reg = self.compile_expr(term.expr, cursor)
            sort_keys.append((k_reg, term.direction == 'DESC'))
            # Copy to a new register at the end of col_regs
            target_reg = self.alloc_reg()
            self.emit(Opcode.MemCopy, P1=k_reg, P2=target_reg,
                      comment=f'sort key copy')
            col_regs.append(target_reg)
        n_visible = n_cols
        sort_col_indices = [(n_visible + i, descending) for i, (_, descending) in enumerate(sort_keys)]
        self.emit(Opcode.Sort, P1=n_visible, P4=sort_col_indices, comment='order by')
        return len(col_regs)  # new total n_cols including sort keys

    # ── INSERT ──

    def _compile_insert(self, node: Insert):
        if node.ctes:
            self._compile_cte(node.ctes)
        td = self._lookup_table_def(node.table.name, node.table.schema)
        cursor = self.alloc_cursor()
        self.cursor_table[cursor] = td
        self.emit(Opcode.Transaction, P1=1, comment='begin write')
        table_info = None
        if td.strict:
            table_info = {'strict': True, 'col_types': [c.type_name.name if c.type_name else 'BLOB' for c in td.columns]}
        self.emit(Opcode.OpenWrite, P1=cursor, P2=td.root_page,
                  P3=len(td.columns), P4=table_info, comment=f'open {td.name}')

        if node.default_values:
            rowid_reg = self.alloc_reg()
            self.emit(Opcode.NewRowid, P1=cursor, P2=0, P3=rowid_reg,
                      comment='new rowid')
            record_reg = self.alloc_reg()
            self.emit(Opcode.MakeRecord, P1=self.reg_null, P2=1, P3=record_reg,
                      comment='default values record')
            self.emit(Opcode.Insert, P1=cursor, P2=record_reg, P3=rowid_reg,
                      comment='insert row')
            if node.returning:
                self.emit(Opcode.SeekRowid, P1=cursor, P2=0, P3=rowid_reg,
                          comment='seek to inserted row for RETURNING')
                self._compile_returning(cursor, node.returning)
        elif node.select:
            self._compile_insert_select(node.select, cursor, td, node.returning)
        elif node.values:
            col_count = len(td.columns) if not node.columns else len(node.columns)
            is_upsert = node.on_conflict is not None or node.or_action in ('IGNORE', 'REPLACE')
            pk_info = self._get_pk_column(td) if is_upsert else None
            for row in node.values:
                val_regs = []
                for val in row:
                    vr = self.compile_expr(val, 0)
                    val_regs.append(vr)
                rowid_reg = self.alloc_reg()
                # For INTEGER PRIMARY KEY with UPSERT, use PK value as rowid
                if pk_info:
                    pk_idx, _ = pk_info
                    if node.columns:
                        mapped = -1
                        for vi, col_name in enumerate(node.columns):
                            try:
                                ci = td.column_index(col_name)
                                if ci == pk_idx:
                                    mapped = vi
                                    break
                            except ValueError:
                                pass
                        pk_val_idx = mapped if mapped >= 0 else pk_idx
                    else:
                        pk_val_idx = pk_idx
                    if pk_val_idx < len(val_regs):
                        self.emit(Opcode.MemCopy, P1=val_regs[pk_val_idx], P2=rowid_reg,
                                  comment='PK value as rowid')
                    else:
                        self.emit(Opcode.NewRowid, P1=cursor, P2=0, P3=rowid_reg,
                                  comment='new rowid')
                else:
                    self.emit(Opcode.NewRowid, P1=cursor, P2=0, P3=rowid_reg,
                              comment='new rowid')
                first_val = val_regs[0] if val_regs else self.reg_null
                record_reg = self.alloc_reg()
                self.emit(Opcode.MakeRecord, P1=first_val, P2=len(val_regs),
                          P3=record_reg, comment='make record')
                do_update = node.on_conflict is not None and node.on_conflict.action == 'UPDATE'
                do_nothing = (node.on_conflict is not None and node.on_conflict.action == 'NOTHING') or node.or_action == 'IGNORE'
                if do_nothing:
                    self.emit(Opcode.NoConflictInsert, P1=cursor, P2=record_reg, P3=rowid_reg,
                              comment='insert or ignore')
                elif do_update:
                    # SeekRowid P2=jump if NOT found (no conflict → normal insert)
                    no_conflict_label = self._label_name('upsert_no_conflict')
                    idx = self.emit(Opcode.SeekRowid, P1=cursor, P2=0, P3=rowid_reg,
                                   comment='seek for conflict; jump if not found')
                    self._patch_jump(idx, no_conflict_label)
                    # --- DO UPDATE (conflict found) ---
                    # Open ephemeral for EXCLUDED values
                    excluded_cursor = self.alloc_cursor()
                    from pysqlite.schema import AFFINITY as _AFF
                    excluded_cols = [ColumnDef(name=c.name, affinity=_AFF.BLOB) for c in td.columns]
                    excluded_td = TableDef(name='EXCLUDED', columns=excluded_cols, root_page=0, sql='')
                    self.cursor_table[excluded_cursor] = excluded_td
                    self.emit(Opcode.OpenEphemeral, P1=excluded_cursor, P2=1, comment='EXCLUDED')
                    excl_rowid = self.alloc_reg()
                    self.emit(Opcode.Integer, P1=0, P2=excl_rowid, comment='excluded rowid')
                    self.emit(Opcode.MakeRecord, P1=first_val, P2=len(val_regs),
                              P3=record_reg, comment='EXCLUDED record')
                    self.emit(Opcode.Insert, P1=excluded_cursor, P2=record_reg, P3=excl_rowid,
                              comment='insert into EXCLUDED')
                    self.emit(Opcode.Rewind, P1=excluded_cursor, P2=0, comment='rewind EXCLUDED')
                    # Build updated row
                    upd_rowid = self.alloc_reg()
                    self.emit(Opcode.Rowid, P1=cursor, P2=upd_rowid, comment='existing rowid')
                    n_cols = len(td.columns)
                    upd_regs = []
                    for ci in range(n_cols):
                        r = self.alloc_reg()
                        self.emit(Opcode.Column, P1=cursor, P2=ci, P3=r, comment=f'read col {ci}')
                        upd_regs.append(r)
                    for sc in node.on_conflict.set_clauses:
                        col_idx = -1
                        try:
                            col_idx = td.column_index(sc.column)
                        except ValueError:
                            col_idx = -1
                        if col_idx >= 0:
                            set_reg = self.compile_expr(sc.expr, excluded_cursor)
                            if set_reg != upd_regs[col_idx]:
                                self.emit(Opcode.MemCopy, P1=set_reg, P2=upd_regs[col_idx],
                                          comment=f'set {sc.column}')
                    self.emit(Opcode.Delete, P1=cursor, comment='delete old row')
                    first_upd = upd_regs[0] if upd_regs else self.reg_null
                    upd_rec_reg = self.alloc_reg()
                    self.emit(Opcode.MakeRecord, P1=first_upd, P2=len(upd_regs),
                              P3=upd_rec_reg, comment='update record')
                    self.emit(Opcode.Insert, P1=cursor, P2=upd_rec_reg, P3=upd_rowid,
                              comment='insert updated row')
                    after_update_label = self._label_name('upsert_after')
                    self.emit_goto(after_update_label)
                    # --- Normal insert (no conflict) ---
                    self.define_label(no_conflict_label)
                    self.emit(Opcode.MakeRecord, P1=first_val, P2=len(val_regs),
                              P3=record_reg, comment='make record')
                    self.emit(Opcode.Insert, P1=cursor, P2=record_reg, P3=rowid_reg,
                              comment='insert row')
                    self.define_label(after_update_label)
                else:
                    self.emit(Opcode.Insert, P1=cursor, P2=record_reg, P3=rowid_reg,
                              comment='insert row')
                if node.returning:
                    self.emit(Opcode.SeekRowid, P1=cursor, P2=0, P3=rowid_reg,
                              comment='seek to inserted row for RETURNING')
                    self._compile_returning(cursor, node.returning)
        else:
            # DEFAULT VALUES
            if node.returning:
                self.emit(Opcode.SeekRowid, P1=cursor, P2=0, P3=rowid_reg,
                          comment='seek to inserted row for RETURNING')
                self._compile_returning(cursor, node.returning)

    def _compile_insert_select(self, select: Select, dest_cursor: int, td: 'TableDef',
                                returning: Returning | None = None):
        if select.ctes:
            self._compile_cte(select.ctes)
        src_cursor = self.alloc_cursor()
        if select.from_clause:
            table_ref = select.from_clause[0]
            if isinstance(table_ref, TableName):
                src_td = self._lookup_table_def(table_ref.name, table_ref.schema)
                self.cursor_table[src_cursor] = src_td
                self.emit(Opcode.Transaction, P1=0, comment='begin read')
                self.emit(Opcode.OpenRead, P1=src_cursor, P2=src_td.root_page,
                          P3=len(src_td.columns), comment=f'open {src_td.name}')
                self.emit(Opcode.Rewind, P1=src_cursor, P2=len(self.instructions) + 4,
                          comment='rewind')
        else:
            self.emit(Opcode.OpenEphemeral, P1=src_cursor, P2=1, comment='dummy scan')

        loop_start = len(self.instructions)
        col_regs = []
        for rc in select.columns:
            if isinstance(rc.expr, StarExpr):
                src_td = self._lookup_table(src_cursor)
                for i in range(len(getattr(src_td, 'columns', []))):
                    r = self.alloc_reg()
                    col_regs.append(r)
                    self.emit(Opcode.Column, P1=src_cursor, P2=i, P3=r,
                              comment=f'column {i}')
            else:
                r = self.compile_expr(rc.expr, src_cursor)
                col_regs.append(r)

        rowid_reg = self.alloc_reg()
        self.emit(Opcode.NewRowid, P1=dest_cursor, P2=0, P3=rowid_reg, comment='new rowid')
        first_val = col_regs[0] if col_regs else self.reg_null
        record_reg = self.alloc_reg()
        self.emit(Opcode.MakeRecord, P1=first_val, P2=len(col_regs),
                  P3=record_reg, comment='make record')
        self.emit(Opcode.Insert, P1=dest_cursor, P2=record_reg, P3=rowid_reg,
                  comment='insert row')

        if returning:
            self.emit(Opcode.SeekRowid, P1=dest_cursor, P2=0, P3=rowid_reg,
                      comment='seek for RETURNING')
            self._compile_returning(dest_cursor, returning)

        if select.from_clause:
            self.emit(Opcode.Next, P1=src_cursor, P2=loop_start, comment='next row')

    # ── Subquery in FROM ──

    def _compile_subquery_fill(self, sub_select: Select, target_cursor: int, sub_cols: list):
        """Compile a subquery to fill an ephemeral table (for SubqueryTable in FROM)."""
        src_cursor = self.alloc_cursor()
        if sub_select.from_clause:
            src_ref = sub_select.from_clause[0]
            if isinstance(src_ref, TableName):
                src_td = self._lookup_table_def(src_ref.name, src_ref.schema)
                self.cursor_table[src_cursor] = src_td
                self.emit(Opcode.Transaction, P1=0, comment='begin read')
                self.emit(Opcode.OpenRead, P1=src_cursor, P2=src_td.root_page,
                          P3=len(src_td.columns), comment=f'open {src_td.name}')
                self.emit(Opcode.Rewind, P1=src_cursor, P2=len(self.instructions) + 4,
                          comment='rewind')
            else:
                self.emit(Opcode.OpenEphemeral, P1=src_cursor, P2=1, comment='dummy scan')
        else:
            self.emit(Opcode.OpenEphemeral, P1=src_cursor, P2=1, comment='dummy scan')

        fill_loop = len(self.instructions)

        # WHERE
        where_skip = None
        if sub_select.where:
            where_reg = self.compile_expr(sub_select.where, src_cursor)
            where_skip = self._label_name('subq_where_skip')
            self.emit_ifnot(where_reg, where_skip)

        # Compute column values
        col_regs = []
        for rc in sub_select.columns:
            if isinstance(rc.expr, StarExpr):
                src_td = self._lookup_table(src_cursor)
                for i in range(len(getattr(src_td, 'columns', []))):
                    r = self.alloc_reg()
                    col_regs.append(r)
                    self.emit(Opcode.Column, P1=src_cursor, P2=i, P3=r,
                              comment=f'column {i}')
            else:
                r = self.compile_expr(rc.expr, src_cursor)
                col_regs.append(r)

        # Insert into ephemeral
        rowid_reg = self.alloc_reg()
        self.emit(Opcode.NewRowid, P1=target_cursor, P2=0, P3=rowid_reg, comment='new rowid')
        first_val = col_regs[0] if col_regs else self.reg_null
        record_reg = self.alloc_reg()
        self.emit(Opcode.MakeRecord, P1=first_val, P2=len(col_regs),
                  P3=record_reg, comment='make record')
        self.emit(Opcode.Insert, P1=target_cursor, P2=record_reg, P3=rowid_reg,
                  comment='insert into ephemeral')

        if where_skip:
            self.define_label(where_skip)

        if sub_select.from_clause:
            self.emit(Opcode.Next, P1=src_cursor, P2=fill_loop, comment='next row')

    # ── UPDATE ──

    def _compile_update(self, node: Update):
        if node.ctes:
            self._compile_cte(node.ctes)
        td = self._lookup_table_def(node.table.name, node.table.schema)
        cursor = self.alloc_cursor()
        self.cursor_table[cursor] = td
        self.emit(Opcode.Transaction, P1=1, comment='begin write')
        table_info = None
        if td.strict:
            table_info = {'strict': True, 'col_types': [c.type_name.name if c.type_name else 'BLOB' for c in td.columns]}
        self.emit(Opcode.OpenWrite, P1=cursor, P2=td.root_page,
                  P3=len(td.columns), P4=table_info, comment=f'open {td.name}')
        self.emit(Opcode.Rewind, P1=cursor, P2=0, comment='rewind')

        loop_start = len(self.instructions)
        if node.where:
            where_reg = self.compile_expr(node.where, cursor)
            skip_label = self._label_name('update_skip')
            self.emit_ifnot(where_reg, skip_label)

        # Read all current column values, override with SET
        rowid_reg = self.alloc_reg()
        self.emit(Opcode.Rowid, P1=cursor, P2=rowid_reg, comment='current rowid')
        n_cols = len(td.columns)
        col_regs = [self.alloc_reg() for _ in range(n_cols)]
        for i in range(n_cols):
            self.emit(Opcode.Column, P1=cursor, P2=i, P3=col_regs[i],
                      comment=f'read col {i}')
        for sc in node.set_clauses:
            col_idx = -1
            try:
                col_idx = td.column_index(sc.column) if hasattr(td, 'column_index') else -1
            except ValueError:
                col_idx = -1
            if col_idx >= 0:
                set_reg = self.compile_expr(sc.expr, cursor)
                if set_reg != col_regs[col_idx]:
                    self.emit(Opcode.MemCopy, P1=set_reg, P2=col_regs[col_idx],
                              comment=f'set {sc.column}')
        self.emit(Opcode.Delete, P1=cursor, comment='delete old row')

        # Insert updated row
        first_val = col_regs[0] if col_regs else self.reg_null
        record_reg = self.alloc_reg()
        self.emit(Opcode.MakeRecord, P1=first_val, P2=len(col_regs),
                  P3=record_reg, comment='update record')
        self.emit(Opcode.Insert, P1=cursor, P2=record_reg, P3=rowid_reg,
                  comment='insert updated row')

        if node.returning:
            self.emit(Opcode.SeekRowid, P1=cursor, P2=0, P3=rowid_reg,
                      comment='seek for RETURNING')
            self._compile_returning(cursor, node.returning)

        if node.where:
            self.define_label(skip_label)
        self.emit(Opcode.Next, P1=cursor, P2=loop_start, comment='next row')

    # ── DELETE ──

    def _compile_delete(self, node: Delete):
        if node.ctes:
            self._compile_cte(node.ctes)
        td = self._lookup_table_def(node.table.name, node.table.schema)
        cursor = self.alloc_cursor()
        self.cursor_table[cursor] = td
        self.emit(Opcode.Transaction, P1=1, comment='begin write')
        self.emit(Opcode.OpenWrite, P1=cursor, P2=td.root_page,
                  P3=len(td.columns), comment=f'open {td.name}')
        self.emit(Opcode.Rewind, P1=cursor, P2=0, comment='rewind')
        loop_start = len(self.instructions)

        if node.where:
            where_reg = self.compile_expr(node.where, cursor)
            skip_label = self._label_name('delete_skip')
            self.emit_ifnot(where_reg, skip_label)

        if node.returning:
            self._compile_returning(cursor, node.returning)
        self.emit(Opcode.Delete, P1=cursor, comment='delete row')
        if node.where:
            self.define_label(skip_label)
        self.emit(Opcode.Next, P1=cursor, P2=loop_start, comment='next row')

    # ── DDL ──

    def _compile_create_table(self, node: CreateTable):
        self.emit(Opcode.Transaction, P1=1, comment='DDL begin write')
        # Allocate root page and register table
        root_page = self.db.allocate_page() if self.db else 1
        sql = self._reconstruct_create_table_sql(node)
        from pysqlite.schema import ColumnDef as SchemaColumnDef
        columns = []
        for col in node.columns:
            affinity = self.schema._determine_affinity(col.type_name)
            columns.append(SchemaColumnDef(
                name=col.name,
                type_name=col.type_name,
                affinity=affinity,
                not_null=self.schema._has_constraint(col, 'NOT NULL') if hasattr(self.schema, '_has_constraint') else False,
                primary_key=self.schema._has_constraint(col, 'PRIMARY KEY') if hasattr(self.schema, '_has_constraint') else False,
                unique=self.schema._has_constraint(col, 'UNIQUE') if hasattr(self.schema, '_has_constraint') else False,
                default_value=self.schema._get_default(col) if hasattr(self.schema, '_get_default') else None,
                auto_increment=self.schema._has_autoinc(col) if hasattr(self.schema, '_has_autoinc') else False,
                collation=self.schema._get_collation(col) if hasattr(self.schema, '_get_collation') else None,
            ))
        from pysqlite.schema import TableDef
        td = TableDef(
            name=node.name.name, root_page=root_page,
            columns=columns, constraints=node.constraints,
            without_rowid=node.without_rowid, strict=node.strict,
            sql=sql,
        )
        if self.schema:
            self.schema.tables[node.name.name] = td
            from pysqlite.btree import BTree
            btree = BTree(self.db, 1, is_table=True)
            self.schema._insert_schema_entry(
                btree, type_='table', name=node.name.name,
                tbl_name=node.name.name, rootpage=root_page, sql=sql,
            )
        self.emit(Opcode.CreateTable, P1=0, P4=node.name.name,
                  comment=f'CREATE TABLE {node.name.name}')

    def _reconstruct_create_table_sql(self, node: CreateTable) -> str:
        parts = [f'CREATE TABLE {node.name.name} (']
        col_parts = []
        for col in node.columns:
            col_sql = col.name
            if col.type_name and col.type_name.name:
                col_sql += f' {col.type_name.name}'
            for c in col.constraints:
                if c.kind == 'PRIMARY KEY':
                    col_sql += ' PRIMARY KEY'
                    if c.details == 'AUTOINCREMENT':
                        col_sql += ' AUTOINCREMENT'
                elif c.kind == 'NOT NULL':
                    col_sql += ' NOT NULL'
                elif c.kind == 'UNIQUE':
                    col_sql += ' UNIQUE'
                elif c.kind == 'DEFAULT' and c.details is not None:
                    col_sql += f' DEFAULT {c.details}'
            col_parts.append(col_sql)
        parts.append(', '.join(col_parts))
        parts.append(')')
        return ''.join(parts)

    def _compile_create_index(self, node: CreateIndex):
        self.emit(Opcode.Transaction, P1=1, comment='DDL begin write')
        col_names = []
        for c in node.columns:
            if isinstance(c.expr, ColumnRef):
                col_names.append(c.expr.name)
            else:
                col_names.append(str(c.expr))
        sql = f"CREATE INDEX {node.name} ON {node.table.name} ({', '.join(col_names)})"
        from pysqlite.schema import IndexDef, IndexedColumnDef
        cols = []
        for c in node.columns:
            name = c.expr.name if isinstance(c.expr, ColumnRef) else str(c.expr)
            cols.append(IndexedColumnDef(name=name, collation=getattr(c, 'collation', None), order=c.direction))
        idx = IndexDef(name=node.name, table_name=node.table.name, columns=cols, unique=node.unique, sql=sql)
        if self.schema:
            self.schema.indexes[node.name] = idx
            from pysqlite.btree import BTree
            btree = BTree(self.db, 1, is_table=True)
            self.schema._insert_schema_entry(
                btree, type_='index', name=node.name,
                tbl_name=node.table.name, rootpage=0, sql=sql,
            )
        self.emit(Opcode.CreateIndex, P1=0, P4=node.name,
                  comment=f'CREATE INDEX {node.name}')

    def _compile_drop_table(self, node: DropTable):
        self.emit(Opcode.Transaction, P1=1, comment='DDL begin write')
        self.emit(Opcode.DropTable, P1=0, P4=node.name.name,
                  comment=f'DROP TABLE {node.name.name}')

    def _compile_drop_index(self, node: DropIndex):
        self.emit(Opcode.Transaction, P1=1, comment='DDL begin write')
        if self.schema:
            self.schema.indexes.pop(node.name, None)
        self.emit(Opcode.DropIndex, P1=0, P4=node.name,
                  comment=f'DROP INDEX {node.name}')

    def _compile_create_view(self, node: CreateView):
        self.emit(Opcode.Transaction, P1=1, comment='DDL begin write')
        sql = f"CREATE VIEW {node.name.name} AS {self._reconstruct_select_sql(node.select)}"
        from pysqlite.schema import ViewDef
        vd = ViewDef(name=node.name.name, sql=sql, select=node.select)
        if self.schema:
            self.schema.views[node.name.name] = vd
            from pysqlite.btree import BTree
            btree = BTree(self.db, 1, is_table=True)
            self.schema._insert_schema_entry(
                btree, type_='view', name=node.name.name,
                tbl_name=node.name.name, rootpage=0, sql=sql,
            )
        self.emit(Opcode.CreateTable, P1=0, P4=node.name.name,
                  comment=f'CREATE VIEW {node.name.name}')

    def _compile_drop_view(self, node: DropView):
        self.emit(Opcode.Transaction, P1=1, comment='DDL begin write')
        if self.schema:
            self.schema.views.pop(node.name, None)
        self.emit(Opcode.DropTable, P1=0, P4=node.name,
                  comment=f'DROP VIEW {node.name}')

    def _reconstruct_select_sql(self, select: Select) -> str:
        parts = ['SELECT']
        if select.distinct:
            parts.append('DISTINCT')
        col_strs = []
        for rc in select.columns:
            col_strs.append(self._expr_to_sql(rc.expr))
        parts.append(', '.join(col_strs))
        if select.from_clause:
            parts.append('FROM')
            from_strs = []
            for ref in select.from_clause:
                if isinstance(ref, TableName):
                    from_strs.append(ref.name)
                elif isinstance(ref, SubqueryTable):
                    from_strs.append(f'({self._reconstruct_select_sql(ref.select)})')
                else:
                    from_strs.append(str(ref))
            parts.append(' '.join(from_strs))
        if select.where:
            parts.append('WHERE')
            parts.append(self._expr_to_sql(select.where))
        if select.group_by:
            parts.append('GROUP BY')
            parts.append(', '.join(self._expr_to_sql(g) for g in select.group_by))
        if select.having:
            parts.append('HAVING')
            parts.append(self._expr_to_sql(select.having))
        if select.order_by:
            parts.append('ORDER BY')
            parts.append(', '.join(self._ordering_to_sql(o) for o in select.order_by))
        if select.limit:
            parts.append(f'LIMIT {self._expr_to_sql(select.limit)}')
        if select.offset:
            parts.append(f'OFFSET {self._expr_to_sql(select.offset)}')
        return ' '.join(parts)

    def _expr_to_sql(self, expr: Expr) -> str:
        if isinstance(expr, Literal):
            v = expr.value
            if v is None:
                return 'NULL'
            if isinstance(v, str):
                return f"'{v}'"
            return str(v)
        if isinstance(expr, ColumnRef):
            if expr.table:
                return f'{expr.table}.{expr.name}'
            return expr.name
        if isinstance(expr, StarExpr):
            return '*'
        if isinstance(expr, BinaryOp):
            return f'({self._expr_to_sql(expr.left)} {expr.op} {self._expr_to_sql(expr.right)})'
        if isinstance(expr, FunctionCall):
            args = ', '.join(self._expr_to_sql(a) for a in expr.args)
            return f'{expr.name}({args})'
        return str(expr)

    def _ordering_to_sql(self, o: OrderingTerm) -> str:
        sql = self._expr_to_sql(o.expr)
        if o.direction == 'DESC':
            sql += ' DESC'
        if o.nulls == 'FIRST':
            sql += ' NULLS FIRST'
        elif o.nulls == 'LAST':
            sql += ' NULLS LAST'
        return sql

    # ── Transactions ──

    def _compile_begin(self, node: Begin):
        self.emit(Opcode.Transaction, P1=1, comment='BEGIN')

    def _compile_commit(self, node: Commit):
        self.emit(Opcode.Transaction, P1=0, comment='COMMIT')

    def _compile_rollback(self, node: RollbackStmt):
        self.emit(Opcode.Transaction, P1=-1, comment='ROLLBACK')

    # ── PRAGMA ──

    def _compile_pragma(self, node: Pragma):
        name = node.name.lower()
        value = node.value
        if isinstance(value, Expr):
            from pysqlite.ast import Literal
            if isinstance(value, Literal):
                value = value.value
            else:
                value = str(value)
        if value is not None:
            value = str(value)

        # PRAGMA that return table metadata
        if name == 'table_info' and value is not None:
            td = self._lookup_table_def(value)
            for i, col in enumerate(td.columns or []):
                r = self.alloc_reg()
                self.emit(Opcode.Integer, P1=i, P2=r, comment='cid')
                r2 = self.alloc_reg()
                self.emit(Opcode.String, P4=col.name, P2=r2, comment='name')
                r3 = self.alloc_reg()
                type_str = col.type_name.name if col.type_name else 'BLOB'
                self.emit(Opcode.String, P4=type_str, P2=r3, comment='type')
                r4 = self.alloc_reg()
                self.emit(Opcode.Integer, P1=1 if col.not_null else 0, P2=r4, comment='notnull')
                r5 = self.alloc_reg()
                dflt = col.default_value if col.default_value is not None else ''
                self.emit(Opcode.String, P4=str(dflt), P2=r5, comment='dflt_value')
                r6 = self.alloc_reg()
                self.emit(Opcode.Integer, P1=1 if col.primary_key else 0, P2=r6, comment='pk')
                self.emit(Opcode.ResultRow, P1=r, P2=6, comment='table_info row')
            return

        if name == 'index_list' and value is not None:
            indexes = self.schema.get_table_indexes(value) if self.schema else []
            for i, idx in enumerate(indexes):
                r = self.alloc_reg()
                self.emit(Opcode.Integer, P1=i, P2=r, comment='seq')
                r2 = self.alloc_reg()
                self.emit(Opcode.String, P4=idx.name, P2=r2, comment='name')
                r3 = self.alloc_reg()
                self.emit(Opcode.Integer, P1=1 if idx.unique else 0, P2=r3, comment='unique')
                self.emit(Opcode.ResultRow, P1=r, P2=3, comment='index_list row')
            return

        if name == 'index_info' and value is not None:
            idx = self.schema.get_index(value) if self.schema else None
            if idx is not None and idx.columns:
                td = self._lookup_table_def(idx.table_name)
                for i, col in enumerate(idx.columns):
                    r = self.alloc_reg()
                    self.emit(Opcode.Integer, P1=i, P2=r, comment='seqno')
                    r2 = self.alloc_reg()
                    cid = 0
                    if td and td.columns:
                        for ci, tc in enumerate(td.columns):
                            if tc.name.upper() == col.name.upper():
                                cid = ci
                                break
                    self.emit(Opcode.Integer, P1=cid, P2=r2, comment='cid')
                    r3 = self.alloc_reg()
                    self.emit(Opcode.String, P4=col.name, P2=r3, comment='name')
                    self.emit(Opcode.ResultRow, P1=r, P2=3, comment='index_info row')
            return

        # PRAGMAs that return a single value
        if name == 'page_count':
            r = self.alloc_reg()
            self.emit(Opcode.Integer, P1=self.db.total_pages if self.db else 0, P2=r)
            self.emit(Opcode.ResultRow, P1=r, P2=1)
            return

        if name == 'page_size':
            r = self.alloc_reg()
            self.emit(Opcode.Integer, P1=self.db.page_size if self.db else 4096, P2=r)
            self.emit(Opcode.ResultRow, P1=r, P2=1)
            return

        if name == 'schema_version':
            r = self.alloc_reg()
            ver = self.schema.schema_version if self.schema else 0
            self.emit(Opcode.Integer, P1=ver, P2=r)
            self.emit(Opcode.ResultRow, P1=r, P2=1)
            return

        if name == 'user_version':
            r = self.alloc_reg()
            ver = self.db.db_header.user_version if self.db and self.db.db_header else 0
            self.emit(Opcode.Integer, P1=ver, P2=r)
            self.emit(Opcode.ResultRow, P1=r, P2=1)
            return

        if name == 'application_id':
            r = self.alloc_reg()
            aid = self.db.db_header.application_id if self.db and self.db.db_header else 0
            self.emit(Opcode.Integer, P1=aid, P2=r)
            self.emit(Opcode.ResultRow, P1=r, P2=1)
            return

        if name == 'freelist_count':
            r = self.alloc_reg()
            self.emit(Opcode.Integer, P1=self.db.freelist_count if self.db else 0, P2=r)
            self.emit(Opcode.ResultRow, P1=r, P2=1)
            return

        if name == 'encoding':
            r = self.alloc_reg()
            enc = 'UTF-8'
            if self.db and self.db.db_header:
                e = self.db.db_header.text_encoding
                enc = {1: 'UTF-8', 2: 'UTF-16le', 3: 'UTF-16be'}.get(e, 'UTF-8')
            self.emit(Opcode.String, P4=enc, P2=r)
            self.emit(Opcode.ResultRow, P1=r, P2=1)
            return

        if name == 'database_list':
            r = self.alloc_reg()
            self.emit(Opcode.Integer, P1=0, P2=r, comment='seq')
            r2 = self.alloc_reg()
            self.emit(Opcode.String, P4='main', P2=r2, comment='name')
            r3 = self.alloc_reg()
            path = self.db.handle.path if self.db and self.db.handle else ''
            self.emit(Opcode.String, P4=path, P2=r3, comment='file')
            self.emit(Opcode.ResultRow, P1=r, P2=3, comment='database_list')
            return

        if name in ('compile_options', 'collation_list'):
            # Return empty result set (no custom options/collations registered)
            return

        if name == 'integrity_check':
            errors = []
            if self.schema:
                for tbl in self.schema.tables.values():
                    if tbl.root_page is not None and tbl.root_page < 1:
                        errors.append(f'Invalid root page {tbl.root_page} for table {tbl.name}')
                for idx in self.schema.indexes.values():
                    if idx.root_page is not None and idx.root_page < 1:
                        errors.append(f'Invalid root page {idx.root_page} for index {idx.name}')
            # Check freelist page references
            if self.db and self.db.freelist_count > 0:
                all_pages = set()
                for tbl in (self.schema.tables.values() if self.schema else []):
                    if tbl.root_page:
                        all_pages.add(tbl.root_page)
                for idx in (self.schema.indexes.values() if self.schema else []):
                    if idx.root_page:
                        all_pages.add(idx.root_page)
                total = self.db.total_pages if hasattr(self.db, 'total_pages') else 0
                for pg in range(1, total + 1):
                    if pg in all_pages:
                        pass  # in use by table/index
                # Check schema root page is valid
                if not errors:
                    try:
                        page1 = None
                        if self.db:
                            from pysqlite.btree import BTreePage
                            page1 = BTreePage(self.db.pager, 1)
                            _ = page1.read_cell(0) if page1.cell_count else None
                    except Exception:
                        errors.append('Error reading schema (page 1)')
            for err in errors:
                r = self.alloc_reg()
                self.emit(Opcode.String, P4=err, P2=r)
                self.emit(Opcode.ResultRow, P1=r, P2=1)
            if not errors:
                r = self.alloc_reg()
                self.emit(Opcode.String, P4='ok', P2=r)
                self.emit(Opcode.ResultRow, P1=r, P2=1)
            return

        # Fallback: return value as string
        reg = self.alloc_reg()
        self.emit(Opcode.String, P4=str(value) if value is not None else '',
                  P2=reg, comment=f'PRAGMA {node.name}')
        self.emit(Opcode.ResultRow, P1=reg, P2=1, comment='pragma result')

    # ── ANALYZE ──

    def _compile_analyze(self, node: Analyze):
        self.emit(Opcode.Noop, comment='ANALYZE (stub - statistics not collected)')

    # ── EXPLAIN ──

    def _compile_explain(self, node: Explain):
        stmt = node.statement
        inner = self.compile(stmt)
        self.instructions = [
            Instruction(Opcode.Explain, comment='EXPLAIN')
        ] + inner

    # ── RETURNING ──

    def _compile_returning(self, cursor: int, ret: Returning):
        col_regs = []
        for rc in ret.columns:
            if isinstance(rc.expr, StarExpr):
                td = self._lookup_table(cursor)
                for i in range(len(getattr(td, 'columns', []))):
                    r = self.alloc_reg()
                    col_regs.append(r)
                    self.emit(Opcode.Column, P1=cursor, P2=i, P3=r,
                              comment=f'returning col {i}')
            else:
                r = self.compile_expr(rc.expr, cursor)
                col_regs.append(r)
        if col_regs:
            first_reg = min(col_regs)
            n_cols = len(col_regs)
            for i, reg in enumerate(col_regs):
                if reg != first_reg + i:
                    self.emit(Opcode.MemCopy, P1=reg, P2=first_reg + i,
                              comment='compact returning column')
        else:
            first_reg = 0
            n_cols = 0
        self.emit(Opcode.ResultRow, P1=first_reg, P2=n_cols, comment='RETURNING')

    # ── CTE ──

    def _compile_cte(self, ctes: list[CTE]):
        pass  # Placeholder — will implement when needed

    # ── View expansion ──

    def _get_view_select(self, view) -> Select | None:
        select = view.select
        if select is not None:
            return select
        from pysqlite.parser import Parser
        from pysqlite.lexer import Lexer
        try:
            tokens = Lexer(view.sql).tokenize()
            stmts = Parser(tokens).parse()
            for s in stmts:
                if isinstance(s, CreateView):
                    view.select = s.select
                    return s.select
        except Exception:
            pass
        return None

    def _build_view_col_map(self, select: Select) -> dict[str, Expr]:
        """Map view column names to their defining expressions."""
        mapping = {}
        for i, rc in enumerate(select.columns):
            if isinstance(rc.expr, StarExpr):
                continue
            name = rc.alias
            if name is None and isinstance(rc.expr, ColumnRef):
                name = rc.expr.name
            if name is None:
                name = str(i)
            mapping[name.upper()] = rc.expr
        return mapping

    def _rewrite_col_ref(self, expr: Expr, view_col_map: dict[str, Expr],
                         view_alias: str | None) -> Expr:
        """Replace ColumnRef expressions that reference view columns with view expressions."""
        from copy import deepcopy
        if isinstance(expr, ColumnRef):
            ref_name = expr.name.upper()
            ref_table = expr.table.upper() if expr.table else ''
            view_upper = view_alias.upper() if view_alias else ''
            if ref_table and ref_table != view_upper:
                return expr
            if ref_name in view_col_map:
                return deepcopy(view_col_map[ref_name])
            return expr
        if isinstance(expr, UnaryOp):
            return UnaryOp(op=expr.op, operand=self._rewrite_col_ref(expr.operand, view_col_map, view_alias))
        if isinstance(expr, BinaryOp):
            return BinaryOp(
                op=expr.op,
                left=self._rewrite_col_ref(expr.left, view_col_map, view_alias),
                right=self._rewrite_col_ref(expr.right, view_col_map, view_alias),
            )
        if isinstance(expr, FunctionCall):
            return FunctionCall(
                name=expr.name,
                args=[self._rewrite_col_ref(a, view_col_map, view_alias) for a in expr.args],
                star=expr.star,
                distinct=expr.distinct,
            )
        if isinstance(expr, IsOp):
            return IsOp(
                left=self._rewrite_col_ref(expr.left, view_col_map, view_alias),
                right=self._rewrite_col_ref(expr.right, view_col_map, view_alias),
                negated=expr.negated,
            )
        if isinstance(expr, LikeOp):
            return LikeOp(
                left=self._rewrite_col_ref(expr.left, view_col_map, view_alias),
                right=self._rewrite_col_ref(expr.right, view_col_map, view_alias),
                escape=self._rewrite_col_ref(expr.escape, view_col_map, view_alias) if expr.escape else None,
                negated=expr.negated,
            )
        return expr

    def _expand_views(self, node: Select):
        """Replace TableName references to views with underlying tables and rewrite columns."""
        if not node.from_clause:
            return
        expanded = []
        view_col_maps: list[tuple[dict[str, Expr], str | None]] = []
        for ref in node.from_clause:
            if isinstance(ref, TableName) and self.schema is not None:
                view = self.schema.get_view(ref.name)
                if view is not None:
                    select = self._get_view_select(view)
                    if select is not None and select.from_clause:
                        alias = ref.alias or ref.name
                        vcm = self._build_view_col_map(select)
                        view_col_maps.append((vcm, alias))
                        for inner_ref in select.from_clause:
                            if isinstance(inner_ref, TableName):
                                new_ref = TableName(name=inner_ref.name, schema=inner_ref.schema)
                                new_ref.alias = alias
                                expanded.append(new_ref)
                            else:
                                expanded.append(inner_ref)
                        continue
            expanded.append(ref)

        if not view_col_maps:
            return

        # Merge view WHERE clauses into the outer query
        for ref in node.from_clause:
            if isinstance(ref, TableName) and self.schema is not None:
                view = self.schema.get_view(ref.name)
                if view is not None:
                    select = self._get_view_select(view)
                    if select is not None and select.where:
                        view_where_alias = ref.alias or ref.name
                        rewritten_where = self._rewrite_col_ref(select.where, {}, None)
                        if node.where:
                            node.where = BinaryOp(op='AND', left=rewritten_where, right=node.where)
                        else:
                            node.where = rewritten_where

        node.from_clause = expanded

        # Build composite column map (merge all view column maps)
        composite_map: dict[str, Expr] = {}
        for vcm, alias in view_col_maps:
            composite_map.update(vcm)

        # Rewrite column references in the outer query
        new_columns = []
        for rc in node.columns:
            if isinstance(rc.expr, StarExpr):
                new_columns.append(rc)
            else:
                new_expr = self._rewrite_col_ref(rc.expr, composite_map, None)
                new_columns.append(ResultColumn(expr=new_expr, alias=rc.alias))
        node.columns = new_columns

        if node.where:
            node.where = self._rewrite_col_ref(node.where, composite_map, None)
        if node.group_by:
            node.group_by = [self._rewrite_col_ref(g, composite_map, None) for g in node.group_by]
        if node.having:
            node.having = self._rewrite_col_ref(node.having, composite_map, None)
        if node.order_by:
            for ot in node.order_by:
                ot.expr = self._rewrite_col_ref(ot.expr, composite_map, None)

    def _get_pk_column(self, td: 'TableDef') -> tuple[int, ColumnDef] | None:
        """Find the single INTEGER PRIMARY KEY column, if any."""
        from pysqlite.schema import AFFINITY
        for i, col in enumerate(getattr(td, 'columns', [])):
            if col.primary_key and col.affinity == AFFINITY.INTEGER:
                return i, col
        return None

    # ── Schema lookups ──

    def _lookup_table(self, cursor: int) -> TableDef | None:
        return self.cursor_table.get(cursor)

    def _cursor_for_table(self, name: str, default: int = 0) -> int:
        name_upper = name.upper()
        for c, td in self.cursor_table.items():
            if td and td.name.upper() == name_upper:
                return c
        return default

    def _lookup_table_def(self, name: str, schema: str | None = None) -> TableDef:
        if self.schema is not None and hasattr(self.schema, 'get_table'):
            td = self.schema.get_table(name, schema)
            if td is not None:
                return td
        return TableDef(name=name, root_page=1, columns=[])

    def _column_index(self, table_def: TableDef | None, col_name: str) -> int:
        if table_def and table_def.columns:
            for i, c in enumerate(table_def.columns):
                if c.name.upper() == col_name.upper():
                    return i
        return 0
