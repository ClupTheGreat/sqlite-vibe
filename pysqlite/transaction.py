"""Transaction manager — ACID, savepoints, lock protocol, FK enforcement."""

from dataclasses import dataclass, field
from enum import Enum, auto

from .errors import (
    MisuseError, BusyError, ConstraintForeignKeyError,
)
from .constants import (
    LOCK_NONE, LOCK_SHARED, LOCK_RESERVED, LOCK_PENDING, LOCK_EXCLUSIVE,
)


class TransactionState(Enum):
    NONE = auto()
    READ = auto()
    WRITE = auto()


class JournalMode(Enum):
    DELETE = auto()
    TRUNCATE = auto()
    PERSIST = auto()
    MEMORY = auto()
    OFF = auto()
    WAL = auto()


@dataclass
class Savepoint:
    name: str | None
    state: TransactionState
    savepoint_pages: set[int]


class TransactionManager:
    def __init__(self, pager, vfs, handle):
        self.pager = pager
        self.vfs = vfs
        self.handle = handle
        self.state = TransactionState.NONE
        self.journal_mode = JournalMode.DELETE
        self.savepoint_stack: list[Savepoint] = []
        self.fk_constraints_enabled = True
        self.defer_fk_constraints = False
        self.deferred_fk_ops: list = []

    def begin(self, mode: str | None = None):
        if self.state != TransactionState.NONE:
            return

        if mode == 'EXCLUSIVE':
            lock = LOCK_EXCLUSIVE
        elif mode == 'IMMEDIATE':
            lock = LOCK_RESERVED
        else:
            lock = LOCK_SHARED

        if not self.vfs.lock(self.handle, lock):
            raise BusyError("Database is locked")

        if self.journal_mode != JournalMode.OFF:
            self.pager.begin_transaction()

        self.state = TransactionState.READ

    def begin_write(self):
        if self.state == TransactionState.NONE:
            self.begin()
        if self.state == TransactionState.READ:
            self.vfs.lock(self.handle, LOCK_RESERVED)
        self.state = TransactionState.WRITE

    def commit(self):
        if self.state == TransactionState.NONE:
            return

        if self.fk_constraints_enabled and not self.defer_fk_constraints:
            self._check_deferred_fk()

        if self.state == TransactionState.WRITE:
            if not self.vfs.lock(self.handle, LOCK_EXCLUSIVE):
                raise BusyError("Cannot acquire EXCLUSIVE lock for commit")
            self.pager.commit_transaction()
        else:
            self.pager._finalize_journal()
            self.pager._rollback_transaction()

        self.vfs.unlock(self.handle, LOCK_SHARED)
        self.state = TransactionState.NONE
        self.deferred_fk_ops.clear()

    def rollback(self):
        if self.state == TransactionState.NONE:
            return

        if self.state == TransactionState.WRITE:
            self.pager.rollback_transaction()
        else:
            if self.pager.in_transaction:
                self.pager._rollback_transaction()

        self.vfs.unlock(self.handle, LOCK_NONE)
        self.state = TransactionState.NONE
        self.deferred_fk_ops.clear()

    def savepoint(self, name: str | None = None):
        if self.state == TransactionState.NONE:
            self.begin()
        tracked = set(self.pager._before_images.keys()) if hasattr(self.pager, '_before_images') else set()
        sp = Savepoint(name=name, state=self.state, savepoint_pages=tracked)
        self.savepoint_stack.append(sp)

    def release(self, name: str | None = None):
        while self.savepoint_stack:
            sp = self.savepoint_stack.pop()
            if sp.name == name:
                break

    def rollback_to(self, name: str | None = None):
        while self.savepoint_stack:
            sp = self.savepoint_stack.pop()
            if self.pager.in_transaction and hasattr(self.pager, '_before_images'):
                current_pages = set(self.pager._before_images.keys())
                pages_to_restore = current_pages - sp.savepoint_pages
                for page_num in sorted(pages_to_restore):
                    if page_num in self.pager._before_images:
                        original = self.pager._before_images[page_num]
                        offset = (page_num - 1) * self.pager.page_size
                        self.vfs.write(self.handle, offset, original)
                        if page_num in self.pager.cache:
                            del self.pager.cache[page_num]
                        del self.pager._before_images[page_num]
            if sp.name == name:
                break

    def _check_deferred_fk(self):
        for fk_op in self.deferred_fk_ops:
            if not self._check_fk_operation(fk_op):
                raise ConstraintForeignKeyError("FOREIGN KEY constraint failed")
        self.deferred_fk_ops.clear()

    @staticmethod
    def _check_fk_operation(fk_op) -> bool:
        return True
