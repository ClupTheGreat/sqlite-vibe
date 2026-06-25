"""Tests for PRAGMA statements."""

import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestPragmas:
    def test_schema_version(self, db):
        res = db.execute('PRAGMA schema_version')
        assert isinstance(res[0][0], int)

    def test_application_id(self, db):
        res = db.execute('PRAGMA application_id')
        assert isinstance(res[0][0], int)

    def test_integrity_check(self, db):
        db.execute('CREATE TABLE t (a INT)')
        res = db.execute('PRAGMA integrity_check')
        assert res[0][0] == 'ok'

    def test_journal_mode_delete(self, db):
        res = db.execute('PRAGMA journal_mode=DELETE')
        assert res[0][0] == 'DELETE'

    def test_journal_mode_wal(self, db):
        res = db.execute('PRAGMA journal_mode=WAL')
        assert res[0][0] == 'WAL'

    def test_journal_mode_memory(self, db):
        res = db.execute('PRAGMA journal_mode=MEMORY')
        assert res[0][0] == 'MEMORY'

    def test_journal_mode_off(self, db):
        res = db.execute('PRAGMA journal_mode=OFF')
        assert res[0][0] == 'OFF'

    def test_compile_options(self, db):
        res = db.execute('PRAGMA compile_options')
        assert res == []

    def test_collation_list(self, db):
        res = db.execute('PRAGMA collation_list')
        assert res == []

    def test_unknown_pragma(self, db):
        res = db.execute('PRAGMA some_unknown_pragma')
        assert res[0][0] == ''
