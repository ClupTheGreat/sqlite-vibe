"""Tests for B-Tree page management and cursors."""

import pytest
from pysqlite.pager import Pager
from pysqlite.vfs import MemoryVFS
from pysqlite.btree import BTreePage, BTreeCursor, BTree
from pysqlite.cell import TableLeafCell
from pysqlite.constants import (
    PT_LEAF_TABLE, PT_INTERIOR_TABLE, PT_LEAF_INDEX,
    SQLITE_OPEN_READWRITE, SQLITE_OPEN_CREATE, DEFAULT_PAGE_SIZE,
)


@pytest.fixture
def pager():
    vfs = MemoryVFS()
    p = Pager(vfs, ":memory:", SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
    yield p
    p.close()


class TestBTreePage:
    def test_new_leaf_page(self, pager):
        pn = pager.allocate_page()
        # BTree now initializes root pages (auto-init moved from BTreePage to BTree)
        page = BTreePage(pager, pn)
        assert page.page_type == 0  # zero-filled until BTree initializes it
        assert page.cell_count == 0
        assert page.first_freeblock == 0

    def test_create_leaf_page_type(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)
        assert page.page_type == PT_LEAF_TABLE
        assert page.cell_count == 0
        assert page.cell_content_offset == pager.page_size
        assert page.is_leaf()
        assert page.is_table()

    def test_create_interior_page(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_interior_page(5)
        page = BTreePage(pager, pn)
        assert page.page_type == PT_INTERIOR_TABLE
        assert page.right_child == 5
        assert not page.is_leaf()

    def test_insert_and_read_cell(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)

        cell = TableLeafCell(42, b'test payload')
        cell_data = cell.serialize()

        page.insert_cell(0, cell_data)
        assert page.cell_count == 1

        read_back = page.read_cell(0)
        parsed = TableLeafCell.parse(read_back)
        assert parsed.rowid == 42
        assert parsed.payload == b'test payload'

    def test_insert_multiple_cells(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)

        for i in range(10):
            cell = TableLeafCell(i * 10, f'data_{i}'.encode())
            page.insert_cell(0, cell.serialize())

        assert page.cell_count == 10
        # First inserted (i=9) is at position 0
        cell0 = TableLeafCell.parse(page.read_cell(0))
        assert cell0.rowid == 90

    def test_delete_cell(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)

        cell1 = TableLeafCell(1, b'first').serialize()
        cell2 = TableLeafCell(2, b'second').serialize()
        page.insert_cell(0, cell1)
        page.insert_cell(1, cell2)
        assert page.cell_count == 2

        page.delete_cell(0)
        assert page.cell_count == 1
        remaining = TableLeafCell.parse(page.read_cell(0))
        assert remaining.rowid == 2

    def test_flush_and_reload(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)

        cell = TableLeafCell(99, b'flush test').serialize()
        page.insert_cell(0, cell)
        page.flush()

        re_read = BTreePage(pager, pn)
        assert re_read.cell_count == 1
        parsed = TableLeafCell.parse(re_read.read_cell(0))
        assert parsed.rowid == 99
        assert parsed.payload == b'flush test'

    def test_freeblock_reuse(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)

        for i in range(5):
            cell = TableLeafCell(i, b'x' * 100).serialize()
            page.insert_cell(i, cell)

        page.delete_cell(2)
        assert page.first_freeblock != 0

        new_cell = TableLeafCell(999, b'y' * 50).serialize()
        page.insert_cell(2, new_cell)
        parsed = TableLeafCell.parse(page.read_cell(2))
        assert parsed.rowid == 999


class TestBTreeCursor:
    def test_cursor_empty(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        cur = btree.cursor()
        cur.first()
        assert cur.eof or cur.bof

    def test_cursor_single_entry(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)
        page.insert_cell(0, TableLeafCell(1, b'data').serialize())
        page.flush()
        btree.root_page = pn

        cur = btree.cursor()
        cur.first()
        assert not cur.eof
        assert cur.current_key() == 1
        assert cur.current_payload() == b'data'

    def test_cursor_next(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)

        for i in range(5):
            cell = TableLeafCell(i, f'row_{i}'.encode()).serialize()
            page.insert_cell(page.cell_count, cell)
        page.flush()
        btree.root_page = pn

        cur = btree.cursor()
        cur.first()
        keys = []
        while not cur.eof:
            keys.append(cur.current_key())
            cur.next()
        assert keys == [0, 1, 2, 3, 4]

    def test_cursor_seek_exact(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)

        for i in range(0, 100, 10):
            cell = TableLeafCell(i, b'data').serialize()
            page.insert_cell(page.cell_count, cell)
        page.flush()
        btree.root_page = pn

        cur = btree.cursor()
        found = cur.seek(50)
        assert found
        assert cur.current_key() == 50

    def test_cursor_seek_insertion_point(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)

        for i in range(0, 100, 10):
            cell = TableLeafCell(i, b'data').serialize()
            page.insert_cell(page.cell_count, cell)
        page.flush()
        btree.root_page = pn

        cur = btree.cursor()
        found = cur.seek(55)
        assert not found
        assert cur.current_key() == 60  # first key >= 55


class TestBTreeInsert:
    def test_simple_insert(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn

        cur = btree.cursor()
        cur.insert(key=42, rowid=42, payload=b'hello')

        cur.first()
        assert cur.current_key() == 42
        assert cur.current_payload() == b'hello'
        cur.close()

    def test_insert_multiple_ordered(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn

        cur = btree.cursor()
        for i in [3, 1, 4, 1, 5, 9]:
            cur.insert(key=i, rowid=i, payload=str(i).encode())

        cur.first()
        keys = []
        while not cur.eof:
            keys.append(cur.current_key())
            cur.next()
        assert keys == sorted([3, 1, 4, 1, 5, 9])

    def test_insert_causes_split(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn

        cur = btree.cursor()
        for i in range(200):
            cur.insert(key=i, rowid=i, payload=b'x' * 50)

        cur.first()
        keys = []
        while not cur.eof:
            keys.append(cur.current_key())
            cur.next()
        assert keys == list(range(200))
        assert btree.root_page != pn  # root should have changed due to splits


class TestBTreeOverflow:
    def test_max_local_payload_size(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        page = BTreePage(pager, pn)
        max_local = page._max_local_payload()
        # For page_size=4096: ((4096-4)*64//100)-4 = 2614
        assert max_local == 2614, f"Expected 2614, got {max_local}"

    def test_insert_small_payload_no_overflow(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        cur = btree.cursor()
        cur.insert(key=1, rowid=1, payload=b'a' * 100)
        cur.first()
        assert cur.current_payload() == b'a' * 100

    def test_insert_large_payload_with_overflow(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        payload = b'x' * 3000  # > 2614, triggers overflow
        cur = btree.cursor()
        cur.insert(key=1, rowid=1, payload=payload)
        cur.first()
        assert cur.current_key() == 1
        assert cur.current_payload() == payload

    def test_multiple_overflow_cells(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        cur = btree.cursor()
        for i in range(5):
            payload = b'x' * (2700 + i * 100)
            cur.insert(key=i, rowid=i, payload=payload)
        cur.first()
        for i in range(5):
            assert cur.current_key() == i
            assert cur.current_payload() == b'x' * (2700 + i * 100)
            cur.next()
        assert cur.eof

    def test_overflow_with_split(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        cur = btree.cursor()
        # Insert many large records to force page splits + overflow
        for i in range(50):
            payload = b'y' * (2800 + (i % 5) * 100)
            cur.insert(key=i * 10, rowid=i * 10, payload=payload)
        cur.first()
        keys = []
        while not cur.eof:
            keys.append(cur.current_key())
            cur.next()
        assert keys == sorted([i * 10 for i in range(50)])


class TestBTreeDelete:
    def test_delete_single_entry(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        cur = btree.cursor()
        cur.insert(key=42, rowid=42, payload=b'hello')
        cur.first()
        assert cur.current_key() == 42
        cur.delete()
        assert cur.eof
        cur.first()
        assert cur.eof

    def test_delete_and_reinsert(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        cur = btree.cursor()
        cur.insert(key=1, rowid=1, payload=b'a')
        cur.insert(key=2, rowid=2, payload=b'b')
        cur.seek(1)
        cur.delete()
        cur.first()
        assert cur.current_key() == 2
        # Reinsert deleted key
        cur.insert(key=1, rowid=1, payload=b'new')
        cur.first()
        keys = []
        while not cur.eof:
            keys.append(cur.current_key())
            cur.next()
        assert keys == [1, 2]

    def test_delete_multiple_entries(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        cur = btree.cursor()
        for i in range(30):
            cur.insert(key=i, rowid=i, payload=f'row_{i}'.encode())
        # Delete odd keys
        for i in range(1, 30, 2):
            found = cur.seek(i)
            assert found
            cur.delete()
        cur.first()
        keys = []
        while not cur.eof:
            keys.append(cur.current_key())
            cur.next()
        assert keys == list(range(0, 30, 2))

    def test_delete_all_causes_rebalance(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        cur = btree.cursor()
        # Insert enough to cause splits (multi-level tree)
        for i in range(100):
            cur.insert(key=i, rowid=i, payload=b'x' * 50)
        assert btree.root_page != pn
        # Delete all entries
        cur.first()
        while not cur.eof:
            cur.delete()
            cur.first()
        # After deleting all, tree should be empty
        cur.first()
        assert cur.eof

    def test_delete_from_split_tree(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        cur = btree.cursor()
        for i in range(50):
            cur.insert(key=i, rowid=i, payload=b'x' * 60)
        cur.first()
        # Delete first 10 entries
        for _ in range(10):
            cur.delete()
            cur.first()
        cur.first()
        keys = []
        while not cur.eof:
            keys.append(cur.current_key())
            cur.next()
        assert keys == list(range(10, 50))

    def test_delete_non_existent(self, pager):
        btree = BTree(pager, 1)
        pn = btree.create_leaf_page()
        btree.root_page = pn
        cur = btree.cursor()
        cur.insert(key=1, rowid=1, payload=b'a')
        cur.eof = True
        cur.delete()  # should be no-op
        cur.first()
        assert cur.current_key() == 1
