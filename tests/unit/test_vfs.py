"""Tests for the Virtual File System layer."""

import os
import tempfile
import pytest
from pysqlite.vfs import OSVFS, MemoryVFS, FileHandle
from pysqlite.constants import (
    LOCK_NONE, LOCK_SHARED, LOCK_RESERVED, LOCK_PENDING, LOCK_EXCLUSIVE,
    SQLITE_OPEN_READONLY, SQLITE_OPEN_READWRITE, SQLITE_OPEN_CREATE,
    SYNC_NORMAL, SYNC_FULL, HEADER_SIZE,
)


class TestMemoryVFS:
    def setup_method(self):
        self.vfs = MemoryVFS()

    def test_open_new(self):
        h = self.vfs.open(":memory:", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        assert h.is_memory
        assert h.mem_buffer is not None

    def test_open_existing(self):
        h1 = self.vfs.open("mydb", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        h1.mem_buffer[:4] = b'test'
        h2 = self.vfs.open("mydb", SQLITE_OPEN_READONLY)
        assert h2.mem_buffer is h1.mem_buffer
        assert bytes(h2.mem_buffer[:4]) == b'test'

    def test_read_write(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.write(h, 10, b'hello')
        data = self.vfs.read(h, 10, 5)
        assert data == b'hello'

    def test_read_past_end(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.write(h, 0, b'hello')
        data = self.vfs.read(h, 999, 10)
        assert data == b'\x00' * 10

    def test_read_partial_past_end(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.write(h, 0, b'hello')
        data = self.vfs.read(h, 2, 10)
        assert data[:3] == b'llo', f"expected 'llo', got {data[:3]}"
        assert data[3:] == b'\x00' * 7, f"expected 7 zeros, got {data[3:]}"

    def test_file_size(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        assert self.vfs.file_size(h) == 0
        self.vfs.write(h, 200, b'x' * 50)
        assert self.vfs.file_size(h) == 250

    def test_truncate_shrink(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.write(h, 500, b'data')
        self.vfs.truncate(h, 100)
        assert self.vfs.file_size(h) == 100

    def test_truncate_grow(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.truncate(h, 10000)
        assert self.vfs.file_size(h) == 10000
        data = self.vfs.read(h, 5000, 10)
        assert data == b'\x00' * 10

    def test_sync_noop(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.sync(h, SYNC_FULL)

    def test_lock_escalation(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        assert self.vfs.lock(h, LOCK_SHARED)
        assert h.lock_state == LOCK_SHARED
        assert self.vfs.lock(h, LOCK_RESERVED)
        assert h.lock_state == LOCK_RESERVED
        assert self.vfs.lock(h, LOCK_EXCLUSIVE)
        assert h.lock_state == LOCK_EXCLUSIVE

    def test_unlock(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.lock(h, LOCK_EXCLUSIVE)
        self.vfs.unlock(h, LOCK_NONE)
        assert h.lock_state == LOCK_NONE

    def test_delete(self):
        self.vfs.open("tempdb", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        assert self.vfs.file_exists("tempdb")
        self.vfs.delete("tempdb")
        assert not self.vfs.file_exists("tempdb")

    def test_close(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.close(h)
        assert h.mem_buffer is None

    def test_sector_size(self):
        h = self.vfs.open("test", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        assert self.vfs.sector_size(h) == 512


class TestOSVFS:
    def setup_method(self):
        self.vfs = OSVFS()
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")

    def teardown_method(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass
        try:
            os.remove(self.db_path + "-journal")
        except FileNotFoundError:
            pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def test_open_create(self):
        h = self.vfs.open(self.db_path, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        assert h.fd >= 0
        assert h.path == self.db_path
        assert h.lock_state == LOCK_NONE
        self.vfs.close(h)

    def test_open_readonly_nonexistent(self):
        with pytest.raises(Exception):
            self.vfs.open(os.path.join(self.tmpdir, "nope.db"), SQLITE_OPEN_READONLY)

    def test_read_write_roundtrip(self):
        h = self.vfs.open(self.db_path, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        data = b'hello sqlite world'
        self.vfs.write(h, 100, data)
        read_back = self.vfs.read(h, 100, len(data))
        assert read_back == data
        self.vfs.close(h)

    def test_read_past_end_zeros(self):
        h = self.vfs.open(self.db_path, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        data = self.vfs.read(h, 0, 500)
        assert len(data) == 500
        assert data == b'\x00' * 500
        self.vfs.close(h)

    def test_file_size(self):
        h = self.vfs.open(self.db_path, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        assert self.vfs.file_size(h) == 0
        self.vfs.write(h, 0, b'x' * 1000)
        assert self.vfs.file_size(h) == 1000
        self.vfs.close(h)

    def test_truncate(self):
        h = self.vfs.open(self.db_path, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.write(h, 0, b'x' * 5000)
        self.vfs.truncate(h, 200)
        assert self.vfs.file_size(h) == 200
        self.vfs.close(h)

    def test_sync(self):
        h = self.vfs.open(self.db_path, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.write(h, 0, b'data')
        self.vfs.sync(h, SYNC_FULL)
        self.vfs.sync(h, SYNC_NORMAL)
        self.vfs.close(h)

    def test_delete(self):
        h = self.vfs.open(self.db_path, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.close(h)
        assert self.vfs.file_exists(self.db_path)
        self.vfs.delete(self.db_path)
        assert not self.vfs.file_exists(self.db_path)

    def test_sector_size(self):
        h = self.vfs.open(self.db_path, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        assert isinstance(self.vfs.sector_size(h), int)
        assert self.vfs.sector_size(h) > 0
        self.vfs.close(h)

    @pytest.mark.skip(reason="Windows locking needs refinement")
    def test_lock_shared(self):
        h = self.vfs.open(self.db_path, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        try:
            ok = self.vfs.lock(h, LOCK_SHARED)
            assert ok
            assert h.lock_state == LOCK_SHARED
            self.vfs.unlock(h, LOCK_NONE)
        finally:
            self.vfs.close(h)

    def test_file_exists(self):
        assert not self.vfs.file_exists(self.db_path)
        h = self.vfs.open(self.db_path, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        self.vfs.close(h)
        assert self.vfs.file_exists(self.db_path)
