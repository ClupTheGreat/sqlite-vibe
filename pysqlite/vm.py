"""Virtual machine — executes compiled VDBE programs."""

from dataclasses import dataclass
from typing import Any

from pysqlite.opcode import Instruction, Opcode
from pysqlite.btree import BTree, BTreeCursor
from pysqlite.record import Record
from pysqlite.errors import DatabaseError


class RegisterType:
    NULL = 'NULL'
    INT = 'INT'
    REAL = 'REAL'
    TEXT = 'TEXT'
    BLOB = 'BLOB'


@dataclass
class Register:
    type: str = RegisterType.NULL
    value: Any = None

    def __repr__(self):
        if self.type == RegisterType.TEXT:
            return f"'{self.value}'"
        return str(self.value)


def make_register(value: Any) -> Register:
    if value is None:
        return Register(RegisterType.NULL)
    if isinstance(value, bool):
        return Register(RegisterType.INT, 1 if value else 0)
    if isinstance(value, int):
        return Register(RegisterType.INT, value)
    if isinstance(value, float):
        return Register(RegisterType.REAL, value)
    if isinstance(value, str):
        return Register(RegisterType.TEXT, value)
    if isinstance(value, bytes):
        return Register(RegisterType.BLOB, value)
    return Register(RegisterType.TEXT, str(value))


@dataclass
class Cursor:
    btree: BTree
    cursor: BTreeCursor
    is_writable: bool = False
    is_open: bool = True
    eof: bool = False
    bof: bool = True
    row: list[Register] | None = None
    strict: bool = False
    col_types: list[str] | None = None  # for STRICT validation

    @property
    def root_page(self) -> int:
        return self.btree.root_page


class VmError(DatabaseError):
    pass


class VM:
    def __init__(self, pager, tx=None, custom_functions=None, custom_aggregates=None):
        self.pager = pager
        self.tx = tx
        self.program: list[Instruction] = []
        self.pc: int = 0
        self.registers: dict[int, Register] = {}
        self.cursors: dict[int, Cursor] = {}
        self.result_rows: list[list] = []
        self.error: str | None = None
        self.last_rowid: int = 0
        self.changes: int = 0
        self.compare_flags: int = 0
        self.agg_accumulators: dict[int, list] = {}
        self.agg_instances: dict[int, Any] = {}
        self.sub_return_stack: list[int] = []
        self.explain_mode: bool = False
        self._current_row: list[Register] = []
        self._affinity_cache: dict[str, int] = {}
        self.sort_spec: list[tuple[int, bool]] = []
        self.agg_spec: dict | None = None
        self.custom_functions: dict[str, callable] = custom_functions or {}
        self.custom_aggregates: dict[str, type] = custom_aggregates or {}
        if self.tx is None:
            from pysqlite.transaction import TransactionManager
            self.tx = TransactionManager(self.pager, self.pager.vfs, self.pager.handle)

    def run(self, program: list[Instruction], params: dict | None = None) -> list[list]:
        self.program = program
        self.pc = 0
        self.registers = {}
        self.cursors = {}
        self.result_rows = []
        self.error = None
        self.last_rowid = 0
        self.changes = 0
        self.compare_flags = 0
        self.agg_accumulators = {}
        self.sub_return_stack = []
        self.explain_mode = False
        self._current_row = []
        self.sort_spec = []
        self.agg_spec = None
        self.params: dict = params or {}

        if self.pager is None:
            self.error = 'No pager available'
            return []

        while self.pc < len(self.program) and self.error is None:
            self.step()

        if self.error:
            raise VmError(self.error)

        if self.explain_mode:
            return self._build_explain_result()

        if self.sort_spec:
            self._sort_results()

        if self.agg_spec:
            self._do_aggregation()

        return self.result_rows

    def _sort_results(self):
        n_visible, sort_cols = self.sort_spec
        def sort_key(row):
            key = []
            for col_idx, descending in sort_cols:
                if col_idx < len(row):
                    v = row[col_idx]
                    if v is None:
                        key.append((1,))
                    else:
                        key.append((0, v if not descending else self._negate(v)))
                else:
                    key.append((1,))
            return key
        self.result_rows.sort(key=sort_key)
        # Strip hidden sort key columns from result
        if n_visible < len(self.result_rows[0]) if self.result_rows else 0:
            self.result_rows = [row[:n_visible] for row in self.result_rows]

    @staticmethod
    def _negate(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return -v
        return v

    def step(self):
        if self.pc >= len(self.program):
            return
        instr = self.program[self.pc]
        self.pc += 1
        handler = getattr(self, f'_op_{instr.opcode}', None)
        if handler is None:
            self.error = f'Unknown opcode: {instr.opcode}'
            return
        try:
            handler(instr.P1, instr.P2, instr.P3, instr.P4, instr.P5)
        except Exception as e:
            self.error = f'Error at pc={self.pc - 1} ({instr.opcode}): {e}'

    # ── Registers ──

    def _reg(self, r: int) -> Register:
        if r not in self.registers:
            self.registers[r] = Register()
        return self.registers[r]

    def _set_reg(self, r: int, value: Register):
        self.registers[r] = value

    def _truthy(self, r: int) -> bool:
        reg = self._reg(r)
        if reg.type == RegisterType.NULL:
            return False
        if reg.type == RegisterType.INT:
            return reg.value != 0
        if reg.type == RegisterType.REAL:
            return reg.value != 0.0
        if reg.type == RegisterType.TEXT:
            return len(reg.value) > 0
        if reg.type == RegisterType.BLOB:
            return len(reg.value) > 0
        return False

    @staticmethod
    def _compare(a: Register, b: Register) -> int:
        """SQLite type ordering: NULL < INT/REAL < TEXT < BLOB."""
        type_order = {RegisterType.NULL: 0, RegisterType.INT: 1,
                      RegisterType.REAL: 1, RegisterType.TEXT: 2,
                      RegisterType.BLOB: 3}
        oa = type_order.get(a.type, 0)
        ob = type_order.get(b.type, 0)
        if oa != ob:
            return -1 if oa < ob else 1
        if a.type == RegisterType.NULL:
            return 0
        if a.type in (RegisterType.INT, RegisterType.REAL):
            va = float(a.value) if a.type == RegisterType.INT else a.value
            vb = float(b.value) if b.type == RegisterType.INT else b.value
            if va < vb:
                return -1
            if va > vb:
                return 1
            return 0
        if a.type == RegisterType.TEXT:
            sa, sb = a.value, b.value
            if sa < sb:
                return -1
            if sa > sb:
                return 1
            return 0
        if a.type == RegisterType.BLOB:
            ba, bb = a.value, b.value
            if ba < bb:
                return -1
            if ba > bb:
                return 1
            return 0
        return 0

    def _compare_branch(self, op: str, left: int, right: int) -> bool:
        cmp = self._compare(self._reg(left), self._reg(right))
        if op == 'Eq':
            return cmp == 0
        if op == 'Ne':
            return cmp != 0
        if op == 'Lt':
            return cmp < 0
        if op == 'Le':
            return cmp <= 0
        if op == 'Gt':
            return cmp > 0
        if op == 'Ge':
            return cmp >= 0
        return False

    # ── Init / Halt ──

    def _op_Init(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if P2 > 0:
            self.pc = P2

    def _op_Halt(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if P1 != 0:
            self.error = str(P4) if P4 else f'Halt error code {P1}'
        self.pc = len(self.program)

    # ── Cursor Operations ──

    def _op_OpenRead(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        btree = BTree(self.pager, P2, is_table=True)
        cursor = btree.cursor()
        c = Cursor(btree=btree, cursor=cursor)
        if isinstance(P4, dict):
            c.strict = P4.get('strict', False)
            c.col_types = P4.get('col_types')
        self.cursors[P1] = c

    def _op_OpenWrite(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        btree = BTree(self.pager, P2, is_table=True)
        cursor = btree.cursor()
        c = Cursor(btree=btree, cursor=cursor, is_writable=True)
        if isinstance(P4, dict):
            c.strict = P4.get('strict', False)
            c.col_types = P4.get('col_types')
        self.cursors[P1] = c

    def _op_OpenEphemeral(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        from pysqlite.pager import Pager
        from pysqlite.vfs import MemoryVFS
        mp = Pager(MemoryVFS(), ':memory:')
        btree = BTree(mp, 1, is_table=True)
        cursor = btree.cursor()
        self.cursors[P1] = Cursor(btree=btree, cursor=cursor, is_writable=True)

    def _op_Close(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if P1 in self.cursors:
            del self.cursors[P1]

    def _op_Rewind(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None:
            return
        c.cursor.first()
        c.eof = c.cursor.eof
        c.bof = c.cursor.bof
        if c.eof and P2 > 0:
            self.pc = P2

    def _op_Next(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None:
            return
        c.cursor.next()
        c.eof = c.cursor.eof
        if not c.eof and P2 > 0:
            self.pc = P2

    def _op_Prev(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None:
            return
        c.cursor.prev()
        c.eof = c.cursor.eof
        if not c.eof and P2 > 0:
            self.pc = P2

    def _op_Last(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None:
            return
        c.cursor.last()
        c.eof = c.cursor.eof

    def _op_SeekRowid(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None:
            return
        key = self._reg(P3).value
        found = c.cursor.seek(key)
        c.eof = not found
        if not found and P2 > 0:
            self.pc = P2

    def _op_SeekGT(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass  # Placeholder

    def _op_SeekGE(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass

    def _op_SeekLT(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass

    def _op_SeekLE(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass

    # ── Record Operations ──

    def _op_Column(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None or c.eof:
            self._set_reg(P3, Register())
            return
        payload = c.cursor.current_payload()
        try:
            record, _ = Record.decode(payload)
            values = record.get_values()
            if P2 < len(values):
                val = values[P2]
                self._set_reg(P3, make_register(val))
            else:
                self._set_reg(P3, Register())
        except Exception:
            self._set_reg(P3, Register())

    def _op_MakeRecord(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        from pysqlite.record import Record as RecordEncoder
        columns = []
        for i in range(P2):
            reg = self._reg(P1 + i)
            st = RecordEncoder.serial_type(reg.value)
            columns.append((st, reg.value))
        rec = RecordEncoder(columns)
        blob = rec.encode()
        self._set_reg(P3, Register(RegisterType.BLOB, blob))

    def _op_Affinity(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass  # Placeholder

    def _op_Cast(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        src = self._reg(P1)
        target_type = str(P4).upper() if P4 else ''
        if target_type in ('INTEGER', 'INT'):
            if src.type == RegisterType.TEXT:
                try:
                    self._set_reg(P3, Register(RegisterType.INT, int(src.value)))
                except (ValueError, TypeError):
                    self._set_reg(P3, Register(RegisterType.INT, 0))
            elif src.type == RegisterType.REAL:
                self._set_reg(P3, Register(RegisterType.INT, int(src.value)))
            else:
                self._set_reg(P3, Register(RegisterType.INT, 0))
        elif target_type in ('REAL', 'FLOAT', 'DOUBLE'):
            if src.type == RegisterType.TEXT:
                try:
                    self._set_reg(P3, Register(RegisterType.REAL, float(src.value)))
                except (ValueError, TypeError):
                    self._set_reg(P3, Register(RegisterType.REAL, 0.0))
            elif src.type == RegisterType.INT:
                self._set_reg(P3, Register(RegisterType.REAL, float(src.value)))
            else:
                self._set_reg(P3, Register(RegisterType.REAL, 0.0))
        elif target_type in ('TEXT',):
            self._set_reg(P3, Register(RegisterType.TEXT, str(src.value if src.value is not None else '')))
        else:
            self._set_reg(P3, src)

    # ── Comparison / Flow Control ──

    def _op_Eq(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if self._compare_branch('Eq', P1, P3) and P2 > 0:
            self.pc = P2

    def _op_Ne(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if self._compare_branch('Ne', P1, P3) and P2 > 0:
            self.pc = P2

    def _op_Lt(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if self._compare_branch('Lt', P1, P3) and P2 > 0:
            self.pc = P2

    def _op_Le(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if self._compare_branch('Le', P1, P3) and P2 > 0:
            self.pc = P2

    def _op_Gt(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if self._compare_branch('Gt', P1, P3) and P2 > 0:
            self.pc = P2

    def _op_Ge(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if self._compare_branch('Ge', P1, P3) and P2 > 0:
            self.pc = P2

    def _op_IsNull(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if self._reg(P1).type == RegisterType.NULL and P2 > 0:
            self.pc = P2

    def _op_NotNull(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if self._reg(P1).type != RegisterType.NULL and P2 > 0:
            self.pc = P2

    def _op_If(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if self._truthy(P1) and P2 > 0:
            self.pc = P2

    def _op_IfNot(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if not self._truthy(P1) and P2 > 0:
            self.pc = P2

    def _op_IfNotZero(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        reg = self._reg(P1)
        if reg.type == RegisterType.INT and reg.value != 0:
            if P3 > 0:
                self._set_reg(P1, Register(RegisterType.INT, reg.value - P3))
            if P2 > 0:
                self.pc = P2

    def _op_Goto(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        target = P1 if P1 > 0 else P2
        if target > 0:
            self.pc = target

    def _op_Gosub(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self.sub_return_stack.append(self.pc)
        if P1 > 0:
            self.pc = P1

    def _op_Return(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if self.sub_return_stack:
            self.pc = self.sub_return_stack.pop()

    # ── Register Management ──

    def _op_Integer(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P2, Register(RegisterType.INT, P1))

    def _op_Int64(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P2, Register(RegisterType.INT, P1))

    def _op_Real(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P2, Register(RegisterType.REAL, P1))

    def _op_String(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P2, Register(RegisterType.TEXT, str(P4) if P4 is not None else ''))

    def _op_Blob(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P2, Register(RegisterType.BLOB, P4 if isinstance(P4, bytes) else b''))

    def _op_Null(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P1, Register())

    def _op_Param(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        name = str(P4) if P4 is not None else ''
        if name in self.params:
            val = self.params[name]
        elif name.lstrip('?:@$') in self.params:
            val = self.params[name.lstrip('?:@$')]
        else:
            try:
                idx = int(name.lstrip('?'))
                key = str(idx)
                if key in self.params:
                    val = self.params[key]
                else:
                    val = None
            except (ValueError, IndexError):
                val = None
        self._set_reg(P2, make_register(val))

    def _op_MemNull(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P1, Register())

    def _op_MemInt(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P1, Register(RegisterType.INT, P2))

    def _op_MemStr(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P1, Register(RegisterType.TEXT, str(P4) if P4 is not None else ''))

    def _op_MemCopy(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        src = self._reg(P1)
        self._set_reg(P2, Register(src.type, src.value))

    def _op_SCopy(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._op_MemCopy(P1, P2, P3, P4, P5)

    def _op_MemMove(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._op_MemCopy(P2, P1, P3, P4, P5)
        self._set_reg(P2, Register())

    def _op_SoftNull(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if P1 in self.registers and self.registers[P1].type != RegisterType.NULL:
            self._set_reg(P1, Register())

    # ── Math opcodes ──

    def _op_Add(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a = self._reg(P1)
        b = self._reg(P3)
        if a.type == RegisterType.NULL or b.type == RegisterType.NULL:
            self._set_reg(P2 if P2 > 0 else P1, Register())
            return
        va = float(a.value) if a.type in (RegisterType.INT, RegisterType.REAL) else 0
        vb = float(b.value) if b.type in (RegisterType.INT, RegisterType.REAL) else 0
        result = va + vb
        self._set_reg(P2 if P2 > 0 else P1, make_register(result))

    def _op_Subtract(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a = self._reg(P1)
        b = self._reg(P3) if P3 > 0 else self._reg(P1 + 1 if P1 < 1000 else 0)
        if a.type == RegisterType.NULL or b.type == RegisterType.NULL:
            self._set_reg(P2 if P2 > 0 else P1, Register())
            return
        va = float(a.value) if a.type in (RegisterType.INT, RegisterType.REAL) else 0
        vb = float(b.value) if b.type in (RegisterType.INT, RegisterType.REAL) else 0
        result = va - vb
        self._set_reg(P2 if P2 > 0 else P1, make_register(result))

    def _op_Multiply(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a, b = self._reg(P1), self._reg(P3)
        dest = P2 if P2 > 0 else P1
        if a.type == RegisterType.NULL or b.type == RegisterType.NULL:
            self._set_reg(dest, Register()); return
        va = float(a.value) if a.type in (RegisterType.INT, RegisterType.REAL) else 0
        vb = float(b.value) if b.type in (RegisterType.INT, RegisterType.REAL) else 0
        self._set_reg(dest, make_register(va * vb))

    def _op_Divide(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a, b = self._reg(P1), self._reg(P3)
        dest = P2 if P2 > 0 else P1
        if a.type == RegisterType.NULL or b.type == RegisterType.NULL:
            self._set_reg(dest, Register()); return
        va = float(a.value) if a.type in (RegisterType.INT, RegisterType.REAL) else 0
        vb = float(b.value) if b.type in (RegisterType.INT, RegisterType.REAL) else 0
        if vb == 0:
            self._set_reg(dest, Register()); return
        self._set_reg(dest, make_register(va / vb))

    def _op_Remainder(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a, b = self._reg(P1), self._reg(P3)
        dest = P2 if P2 > 0 else P1
        if a.type in (RegisterType.NULL, RegisterType.TEXT, RegisterType.BLOB):
            self._set_reg(dest, Register()); return
        if b.type in (RegisterType.NULL, RegisterType.TEXT, RegisterType.BLOB):
            self._set_reg(dest, Register()); return
        va = int(a.value)
        vb = int(b.value)
        if vb == 0:
            self._set_reg(dest, Register()); return
        self._set_reg(dest, Register(RegisterType.INT, va % vb))

    def _op_Concat(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a = self._reg(P1)
        b = self._reg(P3)
        sa = str(a.value) if a.value is not None else ''
        sb = str(b.value) if b.value is not None else ''
        self._set_reg(P2 if P2 > 0 else P1, Register(RegisterType.TEXT, sa + sb))

    def _op_BitAnd(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a, b = self._reg(P1), self._reg(P3)
        dest = P2 if P2 > 0 else P1
        va = int(a.value) if a.type == RegisterType.INT else 0
        vb = int(b.value) if b.type == RegisterType.INT else 0
        self._set_reg(dest, Register(RegisterType.INT, va & vb))

    def _op_BitOr(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a, b = self._reg(P1), self._reg(P3)
        dest = P2 if P2 > 0 else P1
        va = int(a.value) if a.type == RegisterType.INT else 0
        vb = int(b.value) if b.type == RegisterType.INT else 0
        self._set_reg(dest, Register(RegisterType.INT, va | vb))

    def _op_BitNot(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a = self._reg(P1)
        va = int(a.value) if a.type == RegisterType.INT else 0
        self._set_reg(P2, Register(RegisterType.INT, ~va))

    def _op_ShiftLeft(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a, b = self._reg(P1), self._reg(P3)
        va = int(a.value) if a.type == RegisterType.INT else 0
        vb = int(b.value) if b.type == RegisterType.INT else 0
        self._set_reg(P2 if P2 > 0 else P1, Register(RegisterType.INT, va << vb))

    def _op_ShiftRight(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a, b = self._reg(P1), self._reg(P3)
        va = int(a.value) if a.type == RegisterType.INT else 0
        vb = int(b.value) if b.type == RegisterType.INT else 0
        self._set_reg(P2 if P2 > 0 else P1, Register(RegisterType.INT, va >> vb))

    # ── String opcodes ──

    def _op_Length(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a = self._reg(P1)
        self._set_reg(P2, make_register(len(str(a.value)) if a.value is not None else 0))

    def _op_Substr(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        s = str(self._reg(P1).value or '')
        start = int(self._reg(P2).value or 0) if P2 in self.registers else 0
        length = int(self._reg(P3).value or len(s)) if P3 in self.registers else len(s)
        out = s[start - 1:start - 1 + length] if start > 0 else s[:length]
        self._set_reg(P3, Register(RegisterType.TEXT, out))

    def _op_Upper(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a = self._reg(P1)
        self._set_reg(P2, Register(RegisterType.TEXT, str(a.value or '').upper()))

    def _op_Lower(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        a = self._reg(P1)
        self._set_reg(P2, Register(RegisterType.TEXT, str(a.value or '').lower()))

    def _op_Like(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pattern = str(self._reg(P1).value or '')
        text = str(self._reg(P2).value or '') if P2 in self.registers else str(self._reg(P1 + 1).value or '')
        import re
        escaped = re.escape(pattern).replace(r'\%', '%').replace(r'\_', '_')
        regex = '^' + escaped.replace('%', '.*').replace('_', '.') + '$'
        match = bool(re.match(regex, text, re.IGNORECASE))
        self._set_reg(P3, Register(RegisterType.INT, 1 if match else 0))

    def _op_Glob(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pattern = str(self._reg(P1).value or '')
        text = str(self._reg(P2).value or '') if P2 in self.registers else str(self._reg(P1 + 1).value or '')
        import fnmatch
        match = fnmatch.fnmatch(text, pattern)
        self._set_reg(P3, Register(RegisterType.INT, 1 if match else 0))

    # ── I/O ──

    def _op_ResultRow(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        row = []
        for i in range(P2):
            reg = self._reg(P1 + i)
            row.append(reg.value)
        self.result_rows.append(row)

    def _op_ResultColumn(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        reg = self._reg(P1)
        self._current_row.append(reg.value)

    # ── Data modification ──

    def _op_Insert(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._do_insert(P1, P2, P3)

    def _op_NoConflictInsert(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None:
            self.error = 'Cursor not found'
            return
        rowid = self._reg(P3).value if P3 in self.registers else 0
        if not isinstance(rowid, int):
            rowid = 0
        found = c.cursor.seek(rowid)
        if found:
            return  # Conflict - do nothing
        self._do_insert(P1, P2, P3)

    def _do_insert(self, P1, P2, P3):
        c = self.cursors.get(P1)
        if c is None:
            self.error = 'Cursor not found'
            return
        payload = self._reg(P2).value
        if not isinstance(payload, bytes):
            self.error = 'Invalid record for insert'
            return
        if c.strict and c.col_types:
            rec, _ = Record.decode(payload)
            vals = rec.get_values()
            for i, (val, col_type) in enumerate(zip(vals, c.col_types)):
                if col_type and val is not None:
                    if col_type.upper() == 'TEXT' and not isinstance(val, str):
                        self.error = f'STRICT table: expected TEXT for column {i}, got {type(val).__name__}'
                        return
                    if col_type.upper() in ('INTEGER', 'INT') and not isinstance(val, int):
                        self.error = f'STRICT table: expected INTEGER for column {i}, got {type(val).__name__}'
                        return
                    if col_type.upper() == 'REAL' and not isinstance(val, (float, int)):
                        self.error = f'STRICT table: expected REAL for column {i}, got {type(val).__name__}'
                        return
        rowid = self._reg(P3).value if P3 in self.registers else 0
        if not isinstance(rowid, int):
            rowid = 0
        key = rowid
        c.cursor.insert(key, rowid, payload)
        self.changes += 1
        self.last_rowid = rowid

    def _op_Delete(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None or c.eof:
            return
        c.cursor.delete()
        self.changes += 1

    def _op_NewRowid(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None:
            self._set_reg(P3, Register(RegisterType.INT, 1))
            return
        max_rowid = 0
        try:
            c.cursor.last()
            if not c.cursor.eof:
                max_rowid = c.cursor.current_key()
        except Exception:
            pass
        new_id = max(max_rowid + 1, 1)
        self._set_reg(P3, Register(RegisterType.INT, new_id))

    def _op_Rowid(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None or c.eof:
            self._set_reg(P2, Register())
            return
        try:
            key = c.cursor.current_key()
            self._set_reg(P2, Register(RegisterType.INT, key))
        except Exception:
            self._set_reg(P2, Register())

    def _op_RowData(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        c = self.cursors.get(P1)
        if c is None or c.eof:
            self._set_reg(P2, Register())
            return
        try:
            payload = c.cursor.current_payload()
            self._set_reg(P2, Register(RegisterType.BLOB, payload))
        except Exception:
            self._set_reg(P2, Register())

    def _op_Count(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        count = 0
        for c_id, c in self.cursors.items():
            try:
                c.cursor.first()
                while not c.cursor.eof:
                    count += 1
                    c.cursor.next()
            except Exception:
                pass
        self._set_reg(P1, Register(RegisterType.INT, count))

    def _op_Sequence(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P2, make_register(1))

    # ── Functions ──

    def _op_Function(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        func_name = str(P4) if P4 else ''
        args = []
        P1 = max(P1, 0)
        for i in range(P2):
            reg = self._reg(P1 + i)
            args.append(reg.value)
        result = self._call_function(func_name, args)
        self._set_reg(P3, make_register(result))

    def _op_Function0(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._op_Function(P1, P2, P3, P4, P5)

    def _call_function(self, name: str, args: list) -> Any:
        name_upper = name.upper()
        if name_upper in self.custom_functions:
            return self.custom_functions[name_upper](*args)
        if name_upper == 'ABS':
            return abs(args[0]) if args else 0
        if name_upper in ('COALESCE', 'IFNULL'):
            for a in args:
                if a is not None:
                    return a
            return None
        if name_upper == 'NULLIF':
            return None if len(args) >= 2 and args[0] == args[1] else args[0]
        if name_upper == 'TYPEOF':
            if not args:
                return 'null'
            v = args[0]
            if v is None:
                return 'null'
            if isinstance(v, int) and not isinstance(v, bool):
                return 'integer'
            if isinstance(v, float):
                return 'real'
            if isinstance(v, str):
                return 'text'
            if isinstance(v, bytes):
                return 'blob'
            return 'null'
        if name_upper == 'LENGTH':
            s = str(args[0]) if args and args[0] is not None else ''
            return len(s)
        if name_upper == 'UPPER':
            return str(args[0]).upper() if args and args[0] is not None else ''
        if name_upper == 'LOWER':
            return str(args[0]).lower() if args and args[0] is not None else ''
        if name_upper == 'SUBSTR':
            if len(args) < 2:
                return ''
            s = str(args[0] or '')
            start = int(args[1] or 0)
            length = int(args[2]) if len(args) >= 3 and args[2] is not None else len(s)
            return s[start - 1:start - 1 + length] if start > 0 else s[:length]
        if name_upper == 'IFNULL':
            return args[0] if args[0] is not None else args[1] if len(args) > 1 else None
        if name_upper == 'LAST_INSERT_ROWID':
            return self.last_rowid
        if name_upper == 'CHANGES':
            return self.changes
        if name_upper == 'TOTAL_CHANGES':
            return self.changes
        if name_upper == 'RANDOM':
            import random
            return random.randint(-2**63, 2**63 - 1)
        if name_upper == 'ZEROBLOB':
            n = int(args[0]) if args and args[0] is not None else 0
            return b'\x00' * n
        import math
        if name_upper == 'SIN':
            return math.sin(float(args[0])) if args else None
        if name_upper == 'COS':
            return math.cos(float(args[0])) if args else None
        if name_upper == 'TAN':
            return math.tan(float(args[0])) if args else None
        if name_upper == 'ASIN':
            return math.asin(float(args[0])) if args else None
        if name_upper == 'ACOS':
            return math.acos(float(args[0])) if args else None
        if name_upper == 'ATAN':
            return math.atan(float(args[0])) if args else None
        if name_upper == 'CEIL':
            return math.ceil(float(args[0])) if args else None
        if name_upper == 'FLOOR':
            return math.floor(float(args[0])) if args else None
        if name_upper == 'ROUND':
            return round(float(args[0])) if args else None
        if name_upper == 'LOG':
            return math.log(float(args[0])) if args else None
        if name_upper == 'LOG10':
            return math.log10(float(args[0])) if args else None
        if name_upper == 'SQRT':
            return math.sqrt(float(args[0])) if args else None
        if name_upper == 'EXP':
            return math.exp(float(args[0])) if args else None
        if name_upper == 'PI':
            return math.pi
        if name_upper in ('POWER', 'POW'):
            return math.pow(float(args[0]), float(args[1])) if len(args) >= 2 else None
        if name_upper == 'RAND':
            return random.random() * 2 - 1
        if name_upper in ('DATE', 'TIME', 'DATETIME', 'JULIANDAY', 'STRFTIME', 'UNIXEPOCH'):
            return self._call_datetime(name_upper, args)
        if not args:
            return None
        return args[0]

    def _parse_timestring(self, s: str) -> 'datetime.datetime':
        from datetime import datetime, timezone, timedelta
        s = s.strip()
        if s.lower() == 'now':
            return datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            jd = float(s)
            return datetime(1, 1, 1) + timedelta(days=jd - 1721425.5)
        except ValueError:
            pass
        for fmt in ('%Y-%m-%d', '%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
                     '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%d %H:%M:%S.%f'):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        raise ValueError(f"not a valid timestring: {s}")

    def _apply_modifiers(self, dt: 'datetime.datetime', modifiers: list) -> 'datetime.datetime':
        from datetime import datetime, timedelta
        import calendar
        for mod in modifiers:
            m = mod.strip()
            if m == 'start of month':
                dt = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            elif m == 'start of year':
                dt = dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            elif m == 'start of day':
                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            elif m.startswith('weekday '):
                target = int(m[8:])
                current = dt.weekday()
                # weekday 0 = Monday in Python, 0 = Sunday in SQLite
                current_sqlite = (current + 1) % 7
                diff = (target - current_sqlite) % 7
                dt += timedelta(days=diff)
            elif m.startswith('+') or m.startswith('-') or m[0].isdigit():
                parts = m.split()
                if len(parts) >= 2:
                    try:
                        n = int(parts[0])
                    except ValueError:
                        continue
                    unit = parts[1].lower()
                    if unit.startswith('year'):
                        month = dt.month + n * 12
                        year = dt.year + (month - 1) // 12
                        month = ((month - 1) % 12) + 1
                        try:
                            max_day = calendar.monthrange(year, month)[1]
                        except ValueError:
                            max_day = 28  # fallback for very early dates
                        dt = dt.replace(year=year, month=month, day=min(dt.day, max_day))
                    elif unit.startswith('month'):
                        month = dt.month + n
                        year = dt.year + (month - 1) // 12
                        month = ((month - 1) % 12) + 1
                        try:
                            max_day = calendar.monthrange(year, month)[1]
                        except ValueError:
                            max_day = 28
                        dt = dt.replace(year=year, month=month, day=min(dt.day, max_day))
                    elif unit.startswith('day'):
                        dt += timedelta(days=n)
                    elif unit.startswith('hour'):
                        dt += timedelta(hours=n)
                    elif unit.startswith('minute'):
                        dt += timedelta(minutes=n)
                    elif unit.startswith('second'):
                        dt += timedelta(seconds=n)
            elif m == 'localtime':
                import time
                ts = dt.timestamp()
                lt = time.localtime(ts)
                dt = datetime(lt.tm_year, lt.tm_mon, lt.tm_mday,
                              lt.tm_hour, lt.tm_min, lt.tm_sec)
            elif m == 'utc':
                import time
                ts = dt.timestamp()
                ut = time.gmtime(ts)
                dt = datetime(ut.tm_year, ut.tm_mon, ut.tm_mday,
                              ut.tm_hour, ut.tm_min, ut.tm_sec)
        return dt

    def _unixepoch_to_dt(self, ts: float) -> 'datetime.datetime':
        from datetime import datetime, timedelta
        return datetime(1970, 1, 1) + timedelta(seconds=ts)

    def _call_datetime(self, func: str, args: list) -> Any:
        from datetime import datetime, timezone, timedelta
        if func == 'STRFTIME':
            fmt = str(args[0]) if args else ''
            ts = args[1] if len(args) > 1 else 'now'
            mods = [str(a) for a in args[2:]] if len(args) > 2 else []
            if ts is None:
                return None
            if isinstance(ts, (int, float)):
                dt = self._unixepoch_to_dt(float(ts))
            else:
                dt = self._parse_timestring(str(ts))
            dt = self._apply_modifiers(dt, mods)
            return dt.strftime(fmt)
        if not args:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            dt = now
        else:
            ts = args[0]
            modifiers = [str(a) for a in args[1:]] if len(args) > 1 else []
            if ts is None:
                return None
            if isinstance(ts, (int, float)):
                if 'unixepoch' in [str(m).lower() for m in args[1:]]:
                    dt = self._unixepoch_to_dt(float(ts))
                    modifiers_clean = []
                    for m in args[1:]:
                        if str(m).lower() != 'unixepoch':
                            modifiers_clean.append(str(m))
                    modifiers = modifiers_clean
                else:
                    dt = self._parse_timestring(str(ts))
            else:
                dt = self._parse_timestring(str(ts))
            dt = self._apply_modifiers(dt, modifiers)
        if func == 'DATE':
            return dt.strftime('%Y-%m-%d')
        if func == 'TIME':
            return dt.strftime('%H:%M:%S')
        if func == 'DATETIME':
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        if func == 'JULIANDAY':
            return (dt - datetime(1, 1, 1)).days + 1721425.0 + (dt - datetime(1, 1, 1)).seconds / 86400.0
        if func == 'UNIXEPOCH':
            return int((dt - datetime(1970, 1, 1)).total_seconds())
        return None

    # ── EXPLAIN ──

    def _op_Explain(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self.explain_mode = True

    def _build_explain_result(self) -> list[list]:
        rows = []
        for i, instr in enumerate(self.program):
            if instr.opcode == Opcode.Explain:
                continue
            rows.append([i, instr.opcode, instr.P1, instr.P2, instr.P3,
                         str(instr.P4) if instr.P4 is not None else '',
                         instr.P5, instr.comment])
        return rows

    # ── Aggregation ──

    def _op_AggStep(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        args = []
        for i in range(P3):
            reg = self._reg(P2 + i)
            args.append(reg.value)
        func_name = str(P4) if P4 else ''
        name_upper = func_name.upper()
        if name_upper in self.custom_aggregates:
            if P1 not in self.agg_instances:
                self.agg_instances[P1] = self.custom_aggregates[name_upper]()
            agg = self.agg_instances[P1]
            agg.step(*args) if hasattr(agg, 'step') else None
        else:
            if P1 not in self.agg_accumulators:
                self.agg_accumulators[P1] = []
            self.agg_accumulators[P1].append(args)

    def _op_AggFinal(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        func_name = str(P4) if P4 else ''
        name_upper = func_name.upper()
        if name_upper in self.custom_aggregates:
            agg = self.agg_instances.get(P1)
            result = agg.final() if agg and hasattr(agg, 'final') else None
            self._set_reg(P3, make_register(result))
            return
        acc = self.agg_accumulators.get(P1, [])
        result = None
        if name_upper == 'COUNT':
            result = len(acc) if acc else 0
        elif name_upper == 'SUM' or name_upper == 'TOTAL':
            total = 0
            for args in acc:
                v = args[0] if args else 0
                if isinstance(v, (int, float)):
                    total += v
            result = total
        elif name_upper == 'AVG':
            total = 0
            count = 0
            for args in acc:
                v = args[0] if args else 0
                if isinstance(v, (int, float)):
                    total += v
                    count += 1
            result = total / count if count else 0
        elif name_upper == 'MIN':
            values = [args[0] for args in acc if args]
            result = min(values) if values else None
        elif name_upper == 'MAX':
            values = [args[0] for args in acc if args]
            result = max(values) if values else None
        elif name_upper == 'GROUP_CONCAT':
            separator = acc[0][1] if acc and len(acc[0]) > 1 else ','
            values = [str(args[0]) for args in acc if args]
            result = separator.join(values)
        else:
            result = len(acc)
        self._set_reg(P3, make_register(result))

    def _op_AggReset(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self.agg_accumulators.clear()
        self.agg_instances.clear()

    def _op_AggValue(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass

    # ── Transaction ──

    def _op_Transaction(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if P1 == 0:
            self.tx.commit()
        elif P1 == 1:
            self.tx.begin_write()
        elif P1 == -1:
            self.tx.rollback()

    def _op_Savepoint(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self.tx.savepoint(P4)

    def _op_Release(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self.tx.release(P4)

    def _op_RollbackTo(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self.tx.rollback_to(P4)

    # ── DDL ──

    def _op_CreateTable(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass  # Placeholder — will be handled via schema manager

    def _op_CreateIndex(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass

    def _op_DropTable(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass

    def _op_DropIndex(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass

    # ── Noop ──

    def _op_Sort(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if isinstance(P4, list):
            self.sort_spec = (P1, P4)  # (n_visible, [(col_idx, descending), ...])

    def _op_Aggregate(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        if isinstance(P4, dict):
            self.agg_spec = P4

    def _do_aggregation(self):
        spec = self.agg_spec
        if not spec:
            return
        n_visible = spec.get('n_visible', 0)
        group_by_cols = spec.get('group_by', [])
        aggs = spec.get('aggs', [])
        having = spec.get('having', None)
        rows = self.result_rows
        if not rows:
            return

        groups: dict = {}
        for row in rows:
            key = tuple(row[i] if i < len(row) else None for i in group_by_cols) if group_by_cols else ()
            if key not in groups:
                groups[key] = []
            groups[key].append(row)

        result = []
        for key, grp in groups.items():
            group_key = list(key) if group_by_cols else []
            agg_results = []
            for agg in aggs:
                vals = []
                name = agg.get('name', 'COUNT')
                star = agg.get('star', False)
                distinct = agg.get('distinct', False)
                col = agg.get('col', 0)
                n_args = agg.get('n_args', 1)
                if star:
                    vals = [None] * len(grp)
                else:
                    arg_start = agg.get('arg_start', col)
                    for row in grp:
                        v = row[arg_start] if arg_start < len(row) else None
                        vals.append(v)
                if distinct:
                    seen = set()
                    uniq = []
                    for v in vals:
                        if v not in seen:
                            seen.add(v)
                            uniq.append(v)
                    vals = uniq
                result_val = self._compute_aggregate(name, vals, star)
                agg_results.append(result_val)

            if having:
                if not self._eval_having(having, group_key, agg_results):
                    continue

            out = group_key + agg_results
            if group_by_cols and len(out) > n_visible:
                out = out[:n_visible]
            result.append(out)

        if not group_by_cols and aggs and result:
            result = [result[0]]

        self.result_rows = result

    def _eval_having(self, expr, group_key, agg_results):
        if not isinstance(expr, (list, tuple)):
            return bool(expr)
        op = expr[0]
        if op == 'literal':
            val = expr[1]
            return bool(val) if val is not None else False
        elif op == 'column':
            return True  # bare column in HAVING is always true if group exists
        elif op == 'agg_result':
            idx = expr[1]
            if idx < len(agg_results):
                v = agg_results[idx]
                return bool(v) if v is not None else False
            return False
        elif op == 'isnull':
            inner = self._eval_having(expr[1], group_key, agg_results)
            negated = expr[2] if len(expr) > 2 else False
            return not inner if negated else not bool(inner)
        elif op in ('AND', 'and', '&'):
            return self._eval_having(expr[1], group_key, agg_results) and self._eval_having(expr[2], group_key, agg_results)
        elif op in ('OR', 'or', '|'):
            return self._eval_having(expr[1], group_key, agg_results) or self._eval_having(expr[2], group_key, agg_results)
        elif op == 'NOT':
            return not self._eval_having(expr[1], group_key, agg_results)
        elif op in ('=', '==', 'eq', 'Eq'):
            return self._eval_having_val(expr[1], group_key, agg_results) == self._eval_having_val(expr[2], group_key, agg_results)
        elif op in ('<>', '!=', 'ne', 'Ne'):
            return self._eval_having_val(expr[1], group_key, agg_results) != self._eval_having_val(expr[2], group_key, agg_results)
        elif op in ('<', 'lt', 'Lt'):
            left = self._eval_having_val(expr[1], group_key, agg_results)
            right = self._eval_having_val(expr[2], group_key, agg_results)
            return left < right if left is not None and right is not None else False
        elif op in ('<=', 'le', 'Le'):
            left = self._eval_having_val(expr[1], group_key, agg_results)
            right = self._eval_having_val(expr[2], group_key, agg_results)
            return left <= right if left is not None and right is not None else False
        elif op in ('>', 'gt', 'Gt'):
            left = self._eval_having_val(expr[1], group_key, agg_results)
            right = self._eval_having_val(expr[2], group_key, agg_results)
            return left > right if left is not None and right is not None else False
        elif op in ('>=', 'ge', 'Ge'):
            left = self._eval_having_val(expr[1], group_key, agg_results)
            right = self._eval_having_val(expr[2], group_key, agg_results)
            return left >= right if left is not None and right is not None else False
        return True

    def _eval_having_val(self, expr, group_key, agg_results):
        if not isinstance(expr, (list, tuple)):
            return expr
        op = expr[0]
        if op == 'literal':
            return expr[1]
        elif op == 'column':
            return None  # bare columns not evaluated
        elif op == 'agg_result':
            idx = expr[1]
            return agg_results[idx] if idx < len(agg_results) else None
        elif op in ('-',):
            return -self._eval_having_val(expr[1], group_key, agg_results)
        elif op in ('+',):
            return self._eval_having_val(expr[1], group_key, agg_results)
        elif op in ('*',):
            return self._eval_having_val(expr[1], group_key, agg_results) * self._eval_having_val(expr[2], group_key, agg_results)
        elif op in ('/',):
            left = self._eval_having_val(expr[1], group_key, agg_results)
            right = self._eval_having_val(expr[2], group_key, agg_results)
            if right:
                return left / right
            return None
        return None

    def _compute_aggregate(self, name: str, values: list, star: bool = False):
        name_upper = name.upper()
        if name_upper in self.custom_aggregates:
            agg_cls = self.custom_aggregates[name_upper]
            instance = agg_cls()
            for v in values:
                instance.step(v) if hasattr(instance, 'step') else None
            return instance.final() if hasattr(instance, 'final') else None
        if name_upper == 'COUNT':
            if star:
                return len(values)
            return sum(1 for v in values if v is not None)
        elif name_upper in ('SUM', 'TOTAL'):
            total = 0
            for v in values:
                if isinstance(v, (int, float)):
                    total += v
            return total
        elif name_upper == 'AVG':
            total = 0
            count = 0
            for v in values:
                if isinstance(v, (int, float)):
                    total += v
                    count += 1
            return total / count if count else 0
        elif name_upper == 'MIN':
            non_null = [v for v in values if v is not None]
            return min(non_null) if non_null else None
        elif name_upper == 'MAX':
            non_null = [v for v in values if v is not None]
            return max(non_null) if non_null else None
        elif name_upper == 'GROUP_CONCAT':
            if star:
                non_null = [str(v) for v in values]
            else:
                non_null = [str(v) for v in values if v is not None]
            return ','.join(non_null) if non_null else None
        return len(values)

    def _op_Noop(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass

    def _op_Compare(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        pass

    def _op_DecrJumpZero(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        reg = self._reg(P1)
        if reg.type == RegisterType.INT:
            v = reg.value - 1
            self._set_reg(P1, Register(RegisterType.INT, v))
            if v == 0 and P2 > 0:
                self.pc = P2

    def _op_Coalesce(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        for i in range(P1, P1 + P2):
            if self._reg(i).type != RegisterType.NULL:
                self._set_reg(P3, self._reg(i))
                return
        self._set_reg(P3, Register())

    def _op_LastInsertRowid(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P1, Register(RegisterType.INT, self.last_rowid))

    def _op_Changes(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        self._set_reg(P1, Register(RegisterType.INT, self.changes))

    def _op_RealToInt(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        reg = self._reg(P1)
        if reg.type == RegisterType.REAL:
            self._set_reg(P2, Register(RegisterType.INT, int(reg.value)))
        else:
            self._set_reg(P2, reg)

    def _op_IntToReal(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        reg = self._reg(P1)
        if reg.type == RegisterType.INT:
            self._set_reg(P2, Register(RegisterType.REAL, float(reg.value)))
        else:
            self._set_reg(P2, reg)

    def _op_ToText(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        reg = self._reg(P1)
        val = str(reg.value) if reg.value is not None else ''
        self._set_reg(P2 if P2 > 0 else P1, Register(RegisterType.TEXT, val))

    def _op_ToBlob(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        reg = self._reg(P1)
        val = str(reg.value).encode() if reg.value is not None else b''
        self._set_reg(P2 if P2 > 0 else P1, Register(RegisterType.BLOB, val))

    def _op_ToNumeric(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        reg = self._reg(P1)
        if reg.type == RegisterType.TEXT:
            try:
                if '.' in reg.value or 'e' in reg.value.lower():
                    self._set_reg(P2, Register(RegisterType.REAL, float(reg.value)))
                else:
                    self._set_reg(P2, Register(RegisterType.INT, int(reg.value)))
            except (ValueError, TypeError):
                self._set_reg(P2, Register(RegisterType.INT, 0))
        else:
            self._set_reg(P2, reg)

    def _op_ToInt(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        reg = self._reg(P1)
        val = int(reg.value) if reg.type in (RegisterType.INT, RegisterType.REAL) else 0
        self._set_reg(P2, Register(RegisterType.INT, val))

    def _op_ToReal(self, P1: int, P2: int, P3: int, P4: Any, P5: int):
        reg = self._reg(P1)
        val = float(reg.value) if reg.type in (RegisterType.INT, RegisterType.REAL) else 0.0
        self._set_reg(P2, Register(RegisterType.REAL, val))
