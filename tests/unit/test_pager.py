"""Tests for the Pager layer."""

import pytest
from pysqlite.pager import Pager, DatabaseHeader
from pysqlite.vfs import MemoryVFS
from pysqlite.constants import (
    HEADER_SIZE, HEADER_MAGIC, DEFAULT_PAGE_SIZE,
    LOCK_NONE, LOCK_SHARED,
    SQLITE_OPEN_READWRITE, SQLITE_OPEN_CREATE, SQLITE_OPEN_READONLY,
    JournalMode, ENCODING_UTF8,
)
from pysqlite.errors import NotADbError, CorruptError, MisuseError


@pytest.fixture
def memory_pager():
    vfs = MemoryVFS()
    p = Pager(vfs, ":memory:", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
    yield p
    p.close()


class TestPagerInit:
    def test_new_db_header(self, memory_pager):
        assert memory_pager.db_header is not None
        assert memory_pager.db_header.page_size == DEFAULT_PAGE_SIZE
        assert memory_pager.total_pages == 1

    def test_header_magic_written(self, memory_pager):
        header = memory_pager.vfs.read(memory_pager.handle, 0, 16)
        assert header == HEADER_MAGIC

    def test_header_fields(self, memory_pager):
        h = memory_pager.db_header
        assert h.write_format == 1
        assert h.read_format == 1
        assert h.reserved_space == 0
        assert h.file_change_counter == 1
        assert h.database_size == 1
        assert h.freelist_trunk == 0
        assert h.freelist_count == 0
        assert h.schema_cookie == 1
        assert h.schema_format == 4
        assert h.text_encoding == ENCODING_UTF8

    def test_reopen_existing_db(self):
        vfs = MemoryVFS()
        p1 = Pager(vfs, "test.db", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        p1.sync()
        p1.close()

        p2 = Pager(vfs, "test.db", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        assert p2.db_header is not None
        assert p2.total_pages == 1
        assert p2.db_header.page_size == DEFAULT_PAGE_SIZE

    def test_not_a_db(self):
        vfs = MemoryVFS()
        h = vfs.open("bad.db", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        vfs.write(h, 0, b'not a sqlite db' + b'\x00' * 84)
        vfs.close(h)
        with pytest.raises(NotADbError):
            Pager(vfs, "bad.db", SQLITE_OPEN_READWRITE)


class TestPagerReadWrite:
    def test_read_page1(self, memory_pager):
        data = memory_pager.read_page(1)
        assert len(data) == DEFAULT_PAGE_SIZE
        assert data[0:16] == HEADER_MAGIC

    def test_read_page_invalid(self, memory_pager):
        with pytest.raises(CorruptError):
            memory_pager.read_page(0)
        with pytest.raises(CorruptError):
            memory_pager.read_page(999)

    def test_write_and_read_page(self, memory_pager):
        page_data = b'\x42' * DEFAULT_PAGE_SIZE
        memory_pager.write_page(1, page_data)
        read_back = memory_pager.read_page(1)
        assert bytes(read_back) == page_data

    def test_write_new_page(self, memory_pager):
        assert memory_pager.total_pages == 1
        page_num = memory_pager.allocate_page()
        assert page_num == 2
        assert memory_pager.total_pages == 2
        data = memory_pager.read_page(2)
        assert len(data) == DEFAULT_PAGE_SIZE
        assert data == b'\x00' * DEFAULT_PAGE_SIZE

    def test_dirty_set(self, memory_pager):
        assert len(memory_pager.dirty_pages) == 0
        memory_pager.write_page(1, b'\x01' * DEFAULT_PAGE_SIZE)
        assert 1 in memory_pager.dirty_pages

    def test_flush_clears_dirty(self, memory_pager):
        memory_pager.write_page(1, b'\x01' * DEFAULT_PAGE_SIZE)
        memory_pager.flush()
        assert len(memory_pager.dirty_pages) == 0
        assert not memory_pager.cache[1].dirty

    def test_sync(self, memory_pager):
        memory_pager.write_page(1, b'\x01' * DEFAULT_PAGE_SIZE)
        memory_pager.sync()
        assert len(memory_pager.dirty_pages) == 0


class TestPagerCache:
    def test_cache_hit(self, memory_pager):
        data1 = memory_pager.read_page(1)
        data2 = memory_pager.read_page(1)
        assert data1 is data2

    def test_cache_eviction(self, memory_pager):
        memory_pager._clock = 0
        memory_pager._access_time = {}
        memory_pager.read_page(1)
        for i in range(100):
            memory_pager.allocate_page()
            memory_pager.read_page(memory_pager.total_pages)
        assert len(memory_pager.cache) <= 110

    def test_pin_prevents_eviction(self, memory_pager):
        memory_pager.read_page(1)
        memory_pager.pin_page(1)
        for _ in range(200):
            memory_pager._evict_page()
        assert 1 in memory_pager.cache
        memory_pager.unpin_page(1)

    def test_pin_unpin(self, memory_pager):
        assert 1 not in memory_pager.ref_count
        memory_pager.pin_page(1)
        assert memory_pager.ref_count[1] == 1
        memory_pager.pin_page(1)
        assert memory_pager.ref_count[1] == 2
        memory_pager.unpin_page(1)
        assert memory_pager.ref_count[1] == 1
        memory_pager.unpin_page(1)
        assert 1 not in memory_pager.ref_count


class TestPagerTransaction:
    def test_begin_commit(self, memory_pager):
        assert not memory_pager.in_transaction
        memory_pager.begin_transaction()
        assert memory_pager.in_transaction
        memory_pager.commit_transaction()
        assert not memory_pager.in_transaction

    def test_begin_rollback(self, memory_pager):
        memory_pager.write_page(1, b'\xFF' * DEFAULT_PAGE_SIZE)
        memory_pager.flush()
        assert memory_pager.read_page(1)[0] == 0xFF

        memory_pager.begin_transaction()
        memory_pager.write_page(1, b'\x00' * DEFAULT_PAGE_SIZE)
        memory_pager.rollback_transaction()

        assert memory_pager.cache.get(1) is None
        data = memory_pager.read_page(1)
        assert data[0] == 0xFF

    def test_double_begin_raises(self, memory_pager):
        memory_pager.begin_transaction()
        with pytest.raises(MisuseError):
            memory_pager.begin_transaction()
        memory_pager.rollback_transaction()

    def test_commit_nop_when_not_in_txn(self, memory_pager):
        memory_pager.commit_transaction()

    def test_rollback_nop_when_not_in_txn(self, memory_pager):
        memory_pager.rollback_transaction()

    def test_before_images_tracked(self, memory_pager):
        memory_pager.begin_transaction()
        memory_pager._journal_page(1)
        assert 1 in memory_pager._before_images
        memory_pager.rollback_transaction()

    def test_journal_file_created(self, memory_pager):
        assert not memory_pager.vfs.file_exists(":memory:-journal")
        memory_pager.begin_transaction()
        assert memory_pager.vfs.file_exists(":memory:-journal")
        memory_pager.rollback_transaction()

    def test_file_change_counter_increments(self, memory_pager):
        old = memory_pager.file_change_counter
        memory_pager.begin_transaction()
        memory_pager.commit_transaction()
        assert memory_pager.file_change_counter == old + 1


class TestPagerFreelist:
    def test_allocate_from_freelist(self, memory_pager):
        p2 = memory_pager.allocate_page()
        memory_pager.free_page(p2)

        old_total = memory_pager.total_pages
        assert memory_pager.freelist_count > 0

        reused = memory_pager.allocate_page()
        assert reused == old_total
        assert memory_pager.total_pages == old_total
        assert memory_pager.freelist_count == 0

    def test_free_and_reuse(self, memory_pager):
        p2 = memory_pager.allocate_page()
        p3 = memory_pager.allocate_page()
        assert p3 == 3

        memory_pager.free_page(p3)
        assert memory_pager.freelist_count == 1

        reused = memory_pager.allocate_page()
        assert reused == 3
        assert memory_pager.total_pages == 3

    def test_freelist_trunk_chain(self, memory_pager):
        pages = []
        for _ in range(10):
            pages.append(memory_pager.allocate_page())

        for p in pages:
            memory_pager.free_page(p)

        for p in reversed(pages):
            reused = memory_pager.allocate_page()
            assert reused == p

    def test_freelist_headers_updated(self, memory_pager):
        p2 = memory_pager.allocate_page()
        memory_pager.free_page(p2)
        hdr = memory_pager.db_header
        assert hdr.freelist_count == 1
        assert hdr.freelist_trunk == 2


class TestPagerReopen:
    def test_reopen_preserves_data(self):
        vfs = MemoryVFS()
        p1 = Pager(vfs, "test.db", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        p2_no = p1.allocate_page()
        p1.write_page(p2_no, b'\xAB' * DEFAULT_PAGE_SIZE)
        p1.sync()
        p1.close()

        p2 = Pager(vfs, "test.db", SQLITE_OPEN_READWRITE)
        assert p2.read_page(p2_no)[0] == 0xAB
        p2.close()

    def test_reopen_preserves_header_counters(self):
        vfs = MemoryVFS()
        p1 = Pager(vfs, "test.db", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        p1.begin_transaction()
        p1.commit_transaction()
        p1.close()

        p2 = Pager(vfs, "test.db", SQLITE_OPEN_READWRITE)
        assert p2.file_change_counter >= 2
        p2.close()
