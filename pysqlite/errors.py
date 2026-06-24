"""SQLite error codes and exception hierarchy."""


class DatabaseError(Exception):
    """Base for all database errors."""
    def __init__(self, message: str = "", code: int = 1, extended_code: int = 0):
        self.code = code
        self.extended_code = extended_code
        super().__init__(message)


class IOError(DatabaseError):
    def __init__(self, msg="I/O error", code=10, ec=0):
        super().__init__(msg, code, ec)


class CorruptError(DatabaseError):
    def __init__(self, msg="Database corrupted", code=11, ec=0):
        super().__init__(msg, code, ec)


class ConstraintViolation(DatabaseError):
    def __init__(self, msg="Constraint violation", code=19, ec=0):
        super().__init__(msg, code, ec)


class ConstraintPrimaryKeyError(ConstraintViolation):
    def __init__(self, msg="PRIMARY KEY constraint failed"):
        super().__init__(msg, 19, 1555)


class ConstraintUniqueError(ConstraintViolation):
    def __init__(self, msg="UNIQUE constraint failed"):
        super().__init__(msg, 19, 2067)


class ConstraintCheckError(ConstraintViolation):
    def __init__(self, msg="CHECK constraint failed"):
        super().__init__(msg, 19, 275)


class ConstraintNotNullError(ConstraintViolation):
    def __init__(self, msg="NOT NULL constraint failed"):
        super().__init__(msg, 19, 1299)


class ConstraintForeignKeyError(ConstraintViolation):
    def __init__(self, msg="FOREIGN KEY constraint failed"):
        super().__init__(msg, 19, 787)


class ConstraintTriggerError(ConstraintViolation):
    def __init__(self, msg="TRIGGER constraint failed"):
        super().__init__(msg, 19, 1811)


class ReadOnlyError(DatabaseError):
    def __init__(self, msg="Attempt to write to readonly database", code=8):
        super().__init__(msg, code)


class NotADbError(DatabaseError):
    def __init__(self, msg="File is not a database", code=26):
        super().__init__(msg, code)


class SchemaChangedError(DatabaseError):
    def __init__(self, msg="Database schema has changed", code=17):
        super().__init__(msg, code)


class MisuseError(DatabaseError):
    def __init__(self, msg="Library used incorrectly", code=21):
        super().__init__(msg, code)


class FullError(DatabaseError):
    def __init__(self, msg="Database or disk is full", code=13):
        super().__init__(msg, code)


class CantOpenError(DatabaseError):
    def __init__(self, msg="Unable to open database", code=14):
        super().__init__(msg, code)


class LockedError(DatabaseError):
    def __init__(self, msg="Database table is locked", code=6):
        super().__init__(msg, code)


class BusyError(DatabaseError):
    def __init__(self, msg="Database is busy", code=5):
        super().__init__(msg, code)


class NoMemError(DatabaseError):
    def __init__(self, msg="Out of memory", code=7):
        super().__init__(msg, code)


class InterruptError(DatabaseError):
    def __init__(self, msg="Interrupted", code=9):
        super().__init__(msg, code)


class AbortError(DatabaseError):
    def __init__(self, msg="Abort due to ROLLBACK", code=4):
        super().__init__(msg, code)


class MismatchError(DatabaseError):
    def __init__(self, msg="Datatype mismatch", code=20):
        super().__init__(msg, code)


class FormatError(DatabaseError):
    def __init__(self, msg="Format error", code=24):
        super().__init__(msg, code)


class InternalError(DatabaseError):
    def __init__(self, msg="Internal error", code=2):
        super().__init__(msg, code)


class LexerError(DatabaseError):
    def __init__(self, msg="SQL lexer error"):
        super().__init__(msg, 1)


class ParseError(DatabaseError):
    def __init__(self, msg="SQL parse error"):
        super().__init__(msg, 1)


class CompileError(DatabaseError):
    def __init__(self, msg="SQL compile error"):
        super().__init__(msg, 1)


class VMBugError(DatabaseError):
    def __init__(self, msg="Virtual machine error"):
        super().__init__(msg, 1)
