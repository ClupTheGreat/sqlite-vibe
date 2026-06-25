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
    def __init__(self, pager, vfs, handle, schema=None):
        self.pager = pager
        self.vfs = vfs
        self.handle = handle
        self.schema = schema
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
        if not self.schema:
            return
        from pysqlite.btree import BTree
        from pysqlite.record import Record
        from pysqlite.ast import Literal as AstLiteral
        violations = []
        for child_name, child_td in list(self.schema.tables.items()):
            if not child_td.foreign_keys:
                continue
            child_bt = BTree(self.pager, child_td.root_page, is_table=True)
            child_cursor = child_bt.cursor()
            child_cursor.first()
            while not child_cursor.eof:
                payload = child_cursor.current_payload()
                rec, _ = Record.decode(payload)
                child_vals = rec.get_values()
                rowid = child_cursor.current_key()
                found_fk = False
                for fk in child_td.foreign_keys:
                    any_null = False
                    for fk_col in fk.columns:
                        try:
                            c_idx = child_td.column_index(fk_col)
                            if c_idx < len(child_vals) and child_vals[c_idx] is None:
                                any_null = True
                                break
                        except ValueError:
                            pass
                    if any_null:
                        continue
                    parent_td = self.schema.get_table(fk.table)
                    if not parent_td:
                        continue
                    parent_bt = BTree(self.pager, parent_td.root_page, is_table=True)
                    parent_cursor = parent_bt.cursor()
                    parent_found = False
                    parent_cursor.first()
                    while not parent_cursor.eof:
                        ppayload = parent_cursor.current_payload()
                        prec, _ = Record.decode(ppayload)
                        pvals = prec.get_values()
                        all_match = True
                        for i, fk_col in enumerate(fk.columns):
                            try:
                                c_idx = child_td.column_index(fk_col)
                                p_col = fk.parent_columns[i] if i < len(fk.parent_columns) else fk_col
                                p_idx = parent_td.column_index(p_col)
                            except ValueError:
                                all_match = False
                                break
                            if child_vals[c_idx] != pvals[p_idx]:
                                all_match = False
                                break
                        if all_match:
                            parent_found = True
                            break
                        parent_cursor.next()
                    if not parent_found:
                        action = fk.actions.get('DELETE', 'RESTRICT')
                        if action in ('CASCADE', 'SET NULL', 'SET DEFAULT'):
                            violations.append((child_name, child_td, child_bt, rowid, child_vals, action, fk))
                            found_fk = True
                            break
                        else:
                            raise ConstraintForeignKeyError("FOREIGN KEY constraint failed")
                child_cursor.next()
        for child_name, child_td, child_bt, rowid, child_vals, action, fk in violations:
            if action == 'CASCADE':
                del_cursor = child_bt.cursor()
                del_cursor.first()
                while not del_cursor.eof:
                    if del_cursor.current_key() == rowid:
                        del_cursor.delete()
                        break
                    del_cursor.next()
            elif action == 'SET NULL':
                del_cursor = child_bt.cursor()
                del_cursor.first()
                while not del_cursor.eof:
                    if del_cursor.current_key() == rowid:
                        new_vals = list(child_vals)
                        for fk_col in fk.columns:
                            try:
                                c_idx = child_td.column_index(fk_col)
                                new_vals[c_idx] = None
                            except ValueError:
                                pass
                        new_rec = Record.encode_from_values(new_vals)
                        del_cursor.delete()
                        child_bt.cursor().insert(rowid, rowid, new_rec)
                        break
                    del_cursor.next()
            elif action == 'SET DEFAULT':
                del_cursor = child_bt.cursor()
                del_cursor.first()
                while not del_cursor.eof:
                    if del_cursor.current_key() == rowid:
                        new_vals = list(child_vals)
                        for fk_col in fk.columns:
                            try:
                                c_idx = child_td.column_index(fk_col)
                                dv = child_td.columns[c_idx].default_value if c_idx < len(child_td.columns) else None
                                if isinstance(dv, AstLiteral):
                                    dv = dv.value
                                new_vals[c_idx] = dv if dv is not None else None
                            except ValueError:
                                pass
                        new_rec = Record.encode_from_values(new_vals)
                        del_cursor.delete()
                        child_bt.cursor().insert(rowid, rowid, new_rec)
                        break
                    del_cursor.next()
        self.deferred_fk_ops.clear()
