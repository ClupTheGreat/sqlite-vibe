"""Tests for errors.py — error hierarchy."""

from pysqlite.errors import (
    DatabaseError, IOError, CorruptError, NotADbError,
    ConstraintViolation, ConstraintPrimaryKeyError, ConstraintUniqueError,
    ConstraintForeignKeyError, MisuseError, BusyError,
    LexerError, ParseError, CompileError, VMBugError,
)


class TestErrors:
    def test_base_error(self):
        e = DatabaseError("test", 1, 2)
        assert str(e) == "test"
        assert e.code == 1
        assert e.extended_code == 2

    def test_constraint_extended_codes(self):
        assert ConstraintPrimaryKeyError().extended_code == 1555
        assert ConstraintUniqueError().extended_code == 2067
        assert ConstraintForeignKeyError().extended_code == 787

    def test_inheritance(self):
        assert issubclass(IOError, DatabaseError)
        assert issubclass(CorruptError, DatabaseError)
        assert issubclass(NotADbError, DatabaseError)
        assert issubclass(ConstraintPrimaryKeyError, ConstraintViolation)
        assert issubclass(ConstraintUniqueError, ConstraintViolation)

    def test_default_codes(self):
        assert BusyError().code == 5
        assert MisuseError().code == 21
        assert LexerError().code == 1
        assert ParseError().code == 1
        assert VMBugError().code == 1
        assert CompileError().code == 1

    def test_custom_message(self):
        msg = "custom error message"
        e = DatabaseError(msg, 99)
        assert str(e) == msg

    def test_raise_and_catch(self):
        try:
            raise ConstraintUniqueError("duplicate key")
        except ConstraintViolation as e:
            assert "duplicate key" in str(e)
        except DatabaseError:
            pytest.fail("Should have been caught by ConstraintViolation")

    def test_extended_code_on_base(self):
        e = DatabaseError("msg", 19, 2067)
        assert e.extended_code == 2067
