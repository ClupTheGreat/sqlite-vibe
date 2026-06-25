"""Tests for the bytecode compiler."""

from pysqlite.compile import Compiler
from pysqlite.opcode import Opcode
from pysqlite.ast import (
    Select, Insert, Update, Delete,
    CreateTable, CreateIndex, DropTable, DropIndex,
    ResultColumn, Literal, ColumnRef, BinaryOp, UnaryOp,
    FunctionCall, CaseExpr, CastExpr, NullLiteral, StarExpr,
    TableName, SetClause, OrderingTerm,
)


def compile_stmt(stmt):
    comp = Compiler(schema=None)
    return comp.compile(stmt)


def test_compile_select_literal():
    stmt = Select(columns=[ResultColumn(Literal(1))])
    prog = compile_stmt(stmt)
    assert len(prog) >= 3
    assert prog[-1].opcode == Opcode.Halt


def test_compile_select_star():
    stmt = Select(columns=[ResultColumn(StarExpr())],
                  from_clause=[TableName('t')])
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_select_column():
    stmt = Select(columns=[ResultColumn(ColumnRef('a'))],
                  from_clause=[TableName('t')])
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_binary_op():
    stmt = Select(columns=[ResultColumn(BinaryOp('+', Literal(1), Literal(2)))])
    prog = compile_stmt(stmt)
    ops = [i.opcode for i in prog]
    # Constant folding turns 1+2 into 3 at compile time
    assert prog[-1].opcode == Opcode.Halt


def test_compile_comparison():
    stmt = Select(columns=[ResultColumn(BinaryOp('=', Literal(1), Literal(1)))])
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_function_call():
    stmt = Select(columns=[ResultColumn(FunctionCall('ABS', [Literal(-5)]))])
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_case_expr():
    stmt = Select(columns=[ResultColumn(
        CaseExpr(whens=[(BinaryOp('=', Literal(1), Literal(1)), Literal(10))],
                 else_expr=Literal(0))
    )])
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_insert():
    stmt = Insert(table=TableName('t'),
                  values=[[Literal(1), Literal(2)]])
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_update():
    stmt = Update(table=TableName('t'),
                  set_clauses=[SetClause('a', Literal(1))],
                  where=BinaryOp('=', ColumnRef('id'), Literal(1)))
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_delete():
    stmt = Delete(table=TableName('t'))
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_create_table():
    stmt = CreateTable(name=TableName('t'))
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_create_index():
    stmt = CreateIndex(name='idx_t_a', table=TableName('t'))
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_drop_table():
    stmt = DropTable(name=TableName('t'))
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_drop_index():
    stmt = DropIndex(name='idx_t_a')
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt


def test_compile_and_or():
    stmt = Select(columns=[ResultColumn(
        BinaryOp('AND', Literal(1), Literal(0))
    )])
    prog = compile_stmt(stmt)
    assert prog[-1].opcode == Opcode.Halt

    stmt2 = Select(columns=[ResultColumn(
        BinaryOp('OR', Literal(0), Literal(1))
    )])
    prog2 = compile_stmt(stmt2)
    assert prog2[-1].opcode == Opcode.Halt
