"""Tests for the virtual machine."""

from pysqlite.vm import VM, Register, RegisterType, make_register
from pysqlite.opcode import Instruction, Opcode
from pysqlite.pager import Pager
from pysqlite.vfs import MemoryVFS


def make_vm():
    return VM(Pager(MemoryVFS(), ':memory:'))


def run_prog(prog):
    vm = make_vm()
    return vm.run(prog)


def test_halt():
    prog = [Instruction(Opcode.Halt)]
    assert run_prog(prog) == []


def test_integer():
    prog = [
        Instruction(Opcode.Integer, P1=42, P2=1),
        Instruction(Opcode.ResultRow, P1=1, P2=1),
        Instruction(Opcode.Halt),
    ]
    assert run_prog(prog) == [[42]]


def test_string():
    prog = [
        Instruction(Opcode.String, P2=1, P4='hello'),
        Instruction(Opcode.ResultRow, P1=1, P2=1),
        Instruction(Opcode.Halt),
    ]
    assert run_prog(prog) == [['hello']]


def test_null():
    prog = [
        Instruction(Opcode.Null, P1=1),
        Instruction(Opcode.ResultRow, P1=1, P2=1),
        Instruction(Opcode.Halt),
    ]
    assert run_prog(prog) == [[None]]


def test_add():
    prog = [
        Instruction(Opcode.Integer, P1=2, P2=1),
        Instruction(Opcode.Integer, P1=3, P2=2),
        Instruction(Opcode.Add, P1=1, P2=3, P3=2),
        Instruction(Opcode.ResultRow, P1=3, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert len(rows) == 1
    assert rows[0][0] == 5.0


def test_subtract():
    prog = [
        Instruction(Opcode.Integer, P1=10, P2=1),
        Instruction(Opcode.Integer, P1=3, P2=2),
        Instruction(Opcode.Subtract, P1=1, P2=3, P3=2),
        Instruction(Opcode.ResultRow, P1=3, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 7.0


def test_multiply():
    prog = [
        Instruction(Opcode.Integer, P1=4, P2=1),
        Instruction(Opcode.Integer, P1=5, P2=2),
        Instruction(Opcode.Multiply, P1=1, P2=3, P3=2),
        Instruction(Opcode.ResultRow, P1=3, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 20.0


def test_divide():
    prog = [
        Instruction(Opcode.Integer, P1=10, P2=1),
        Instruction(Opcode.Integer, P1=3, P2=2),
        Instruction(Opcode.Divide, P1=1, P2=3, P3=2),
        Instruction(Opcode.ResultRow, P1=3, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert abs(rows[0][0] - 3.333) < 0.01


def test_concat():
    prog = [
        Instruction(Opcode.String, P2=1, P4='hello'),
        Instruction(Opcode.String, P2=2, P4=' world'),
        Instruction(Opcode.Concat, P1=1, P2=3, P3=2),
        Instruction(Opcode.ResultRow, P1=3, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 'hello world'


def test_goto():
    prog = [
        Instruction(Opcode.Integer, P1=1, P2=1),       # 0
        Instruction(Opcode.Goto, P2=3),                 # 1 -> jump to 3
        Instruction(Opcode.Integer, P1=99, P2=1),       # 2 skipped
        Instruction(Opcode.ResultRow, P1=1, P2=1),      # 3
        Instruction(Opcode.Halt),                        # 4
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 1


def test_if_true():
    prog = [
        Instruction(Opcode.Integer, P1=1, P2=1),
        Instruction(Opcode.Integer, P1=0, P2=2),
        Instruction(Opcode.If, P1=1, P2=5),  # jump to row 5
        Instruction(Opcode.Integer, P1=99, P2=3),  # skipped
        Instruction(Opcode.Goto, P2=6),
        Instruction(Opcode.Integer, P1=42, P2=3),  # target
        Instruction(Opcode.ResultRow, P1=3, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 42


def test_ifnot():
    prog = [
        Instruction(Opcode.Integer, P1=0, P2=1),
        Instruction(Opcode.Integer, P1=42, P2=2),
        Instruction(Opcode.IfNot, P1=1, P2=4),
        Instruction(Opcode.Goto, P2=5),
        Instruction(Opcode.ResultRow, P1=2, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 42


def test_eq_branch():
    prog = [
        Instruction(Opcode.Integer, P1=5, P2=1),
        Instruction(Opcode.Integer, P1=5, P2=2),
        Instruction(Opcode.Integer, P1=99, P2=3),
        Instruction(Opcode.Eq, P1=1, P2=6, P3=2),  # jump to 6
        Instruction(Opcode.Integer, P1=0, P2=3),  # skip if not eq
        Instruction(Opcode.Goto, P2=7),
        Instruction(Opcode.Integer, P1=1, P2=3),  # target
        Instruction(Opcode.ResultRow, P1=3, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 1


def test_ne_branch():
    prog = [
        Instruction(Opcode.Integer, P1=5, P2=1),
        Instruction(Opcode.Integer, P1=3, P2=2),
        Instruction(Opcode.Ne, P1=1, P2=5, P3=2),
        Instruction(Opcode.Integer, P1=0, P2=3),
        Instruction(Opcode.Goto, P2=6),
        Instruction(Opcode.Integer, P1=1, P2=3),
        Instruction(Opcode.ResultRow, P1=3, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 1


def test_mem_copy():
    prog = [
        Instruction(Opcode.Integer, P1=42, P2=1),
        Instruction(Opcode.MemCopy, P1=1, P2=2),
        Instruction(Opcode.ResultRow, P1=2, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 42


def test_result_row_multi():
    prog = [
        Instruction(Opcode.Integer, P1=10, P2=1),
        Instruction(Opcode.String, P2=2, P4='hello'),
        Instruction(Opcode.ResultRow, P1=1, P2=2),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0] == [10, 'hello']


def test_registers_default_null():
    vm = make_vm()
    reg = vm._reg(42)
    assert reg.type == RegisterType.NULL


def test_register_types():
    r = make_register(None)
    assert r.type == RegisterType.NULL
    r = make_register(42)
    assert r.type == RegisterType.INT
    r = make_register(3.14)
    assert r.type == RegisterType.REAL
    r = make_register('hello')
    assert r.type == RegisterType.TEXT
    r = make_register(b'abc')
    assert r.type == RegisterType.BLOB


def test_is_null():
    prog = [
        Instruction(Opcode.Integer, P1=0, P2=1),
        Instruction(Opcode.ResultRow, P1=1, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 0


def test_bit_ops():
    prog = [
        Instruction(Opcode.Integer, P1=6, P2=1),   # 110
        Instruction(Opcode.Integer, P1=3, P2=2),   # 011
        Instruction(Opcode.BitAnd, P1=1, P2=3, P3=2),
        Instruction(Opcode.ResultRow, P1=3, P2=1),
        Instruction(Opcode.Halt),
    ]
    rows = run_prog(prog)
    assert rows[0][0] == 2  # 110 & 011 = 010 = 2
