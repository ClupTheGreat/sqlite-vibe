"""Tests for transaction manager — savepoints, locks, commit/rollback."""

import pytest
from pysqlite.vfs import MemoryVFS
from pysqlite.pager import Pager
from pysqlite.transaction import (
    TransactionManager, TransactionState, JournalMode, Savepoint,
)
from pysqlite.errors import BusyError


@pytest.fixture
def pager():
    vfs = MemoryVFS()
    return Pager(vfs, ':memory:')


@pytest.fixture
def tx(pager):
    return TransactionManager(pager, pager.vfs, pager.handle)


class TestTransactionState:
    def test_initial_state(self, tx):
        assert tx.state == TransactionState.NONE

    def test_begin(self, tx):
        tx.begin()
        assert tx.state == TransactionState.READ

    def test_begin_write(self, tx):
        tx.begin_write()
        assert tx.state == TransactionState.WRITE

    def test_commit(self, tx):
        tx.begin()
        tx.commit()
        assert tx.state == TransactionState.NONE

    def test_rollback(self, tx):
        tx.begin()
        tx.rollback()
        assert tx.state == TransactionState.NONE

    def test_commit_no_transaction(self, tx):
        tx.commit()
        assert tx.state == TransactionState.NONE

    def test_rollback_no_transaction(self, tx):
        tx.rollback()
        assert tx.state == TransactionState.NONE

    def test_begin_twice(self, tx):
        tx.begin()
        tx.begin()
        assert tx.state == TransactionState.READ


class TestSavepoints:
    def test_create_savepoint(self, tx):
        tx.savepoint('sp1')
        assert len(tx.savepoint_stack) == 1
        assert tx.savepoint_stack[0].name == 'sp1'

    def test_savepoint_auto_begin(self, tx):
        assert tx.state == TransactionState.NONE
        tx.savepoint('sp1')
        assert tx.state != TransactionState.NONE

    def test_release_savepoint(self, tx):
        tx.savepoint('sp1')
        tx.savepoint('sp2')
        tx.release('sp1')
        assert len(tx.savepoint_stack) == 0

    def test_release_inner_only(self, tx):
        tx.savepoint('sp1')
        tx.savepoint('sp2')
        tx.release('sp2')
        assert len(tx.savepoint_stack) == 1
        assert tx.savepoint_stack[0].name == 'sp1'

    def test_rollback_to_savepoint(self, tx):
        tx.savepoint('sp1')
        tx.savepoint('sp2')
        tx.rollback_to('sp1')
        assert len(tx.savepoint_stack) == 0

    def test_savepoint_autoname(self, tx):
        tx.savepoint()
        assert tx.savepoint_stack[0].name is None


class TestStateTransitions:
    def test_read_then_write(self, tx):
        tx.begin()
        assert tx.state == TransactionState.READ
        tx.begin_write()
        assert tx.state == TransactionState.WRITE

    def test_write_commit_cycle(self, tx):
        tx.begin_write()
        assert tx.state == TransactionState.WRITE
        tx.commit()
        assert tx.state == TransactionState.NONE

    def test_write_rollback_cycle(self, tx):
        tx.begin_write()
        tx.rollback()
        assert tx.state == TransactionState.NONE

    def test_read_only_commit(self, tx):
        tx.begin()
        tx.commit()
        assert tx.state == TransactionState.NONE


class TestJournalMode:
    def test_default_mode(self, tx):
        assert tx.journal_mode == JournalMode.DELETE

    def test_off_mode_no_journal(self, tx):
        tx.journal_mode = JournalMode.OFF
        tx.begin()
        assert tx.state == TransactionState.READ


class TestTransactionManager:
    def test_deferred_begin(self, pager):
        tx = TransactionManager(pager, pager.vfs, pager.handle)
        tx.begin()
        assert tx.state == TransactionState.READ

    def test_immediate_begin(self, pager):
        tx = TransactionManager(pager, pager.vfs, pager.handle)
        tx.begin('IMMEDIATE')
        assert tx.state == TransactionState.READ

    def test_exclusive_begin(self, pager):
        tx = TransactionManager(pager, pager.vfs, pager.handle)
        tx.begin('EXCLUSIVE')
        assert tx.state == TransactionState.READ
