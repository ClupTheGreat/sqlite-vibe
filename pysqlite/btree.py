"""B-Tree engine — page management, cursors, split/merge, overflow."""

from .pager import Pager
from .constants import (
    PT_INTERIOR_INDEX, PT_INTERIOR_TABLE, PT_LEAF_INDEX, PT_LEAF_TABLE,
    MAX_EMBEDDED_PAYLOAD_FRACTION, MIN_EMBEDDED_PAYLOAD_FRACTION,
    LEAF_PAYLOAD_FRACTION,
)
from .cell import (
    TableLeafCell, TableInteriorCell, IndexLeafCell, IndexInteriorCell,
)
from .record import Record
from .errors import CorruptError
from .bitwise import encode_varint, decode_varint


class BTreePage:
    """A single B-Tree page with parsed header and cell pointer array."""

    __slots__ = (
        'pager', 'page_number', 'page_type', 'first_freeblock',
        'cell_count', 'cell_content_offset', 'fragmented_free_bytes',
        'right_child', 'cell_pointers', 'raw_data', 'dirty',
    )

    DB_HEADER_SIZE = 100

    def __init__(self, pager: 'Pager', page_number: int):
        self.pager = pager
        self.page_number = page_number
        self.raw_data = bytearray(pager.read_page(page_number))
        self.dirty = False
        self._parse_header()
        self._parse_cell_pointers()

    @property
    def b_tree_offset(self) -> int:
        return self.DB_HEADER_SIZE if self.page_number == 1 else 0

    def _parse_header(self):
        off = self.b_tree_offset
        data = self.raw_data
        self.page_type = data[off + 0]
        self.first_freeblock = int.from_bytes(data[off + 1:off + 3], 'big')
        self.cell_count = int.from_bytes(data[off + 3:off + 5], 'big')
        self.cell_content_offset = int.from_bytes(data[off + 5:off + 7], 'big')
        self.fragmented_free_bytes = data[off + 7]

        if self.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX):
            self.right_child = int.from_bytes(data[off + 8:off + 12], 'big')
        else:
            self.right_child = 0

    def _write_header(self):
        off = self.b_tree_offset
        data = self.raw_data
        data[off + 0] = self.page_type
        data[off + 1:off + 3] = self.first_freeblock.to_bytes(2, 'big')
        data[off + 3:off + 5] = self.cell_count.to_bytes(2, 'big')
        data[off + 5:off + 7] = self.cell_content_offset.to_bytes(2, 'big')
        data[off + 7] = self.fragmented_free_bytes

        if self.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX):
            data[off + 8:off + 12] = self.right_child.to_bytes(4, 'big')
        self.dirty = True

    def _parse_cell_pointers(self):
        off = self.b_tree_offset
        self.cell_pointers = []
        base = 12 if self.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX) else 8
        for i in range(self.cell_count):
            idx = off + base + (i * 2)
            ptr = int.from_bytes(self.raw_data[idx:idx + 2], 'big')
            self.cell_pointers.append(ptr)

    def read_cell(self, index: int) -> bytes:
        """Read the raw bytes of cell at given index."""
        if index < 0 or index >= self.cell_count:
            raise IndexError(f"Cell index {index} out of range (count: {self.cell_count})")
        ptr = self.cell_pointers[index]
        end_ptr = self._find_cell_end(index)
        return bytes(self.raw_data[ptr:end_ptr])

    def _find_cell_end(self, index: int) -> int:
        ptr = self.cell_pointers[index]
        next_higher = self.pager.page_size
        for i in range(self.cell_count):
            cp = self.cell_pointers[i]
            if ptr < cp < next_higher:
                next_higher = cp
        return next_higher

    def insert_cell(self, index: int, cell_data: bytes) -> bool:
        if self._needs_defrag():
            self._defragment()
        cell_offset = self._allocate_space(len(cell_data))
        if cell_offset == -1:
            return False
        self.raw_data[cell_offset:cell_offset + len(cell_data)] = cell_data
        for i in range(self.cell_count, index, -1):
            src = self._pointer_offset(i - 1)
            dst = self._pointer_offset(i)
            self.raw_data[dst:dst + 2] = self.raw_data[src:src + 2]
        ptr_offset = self._pointer_offset(index)
        self.raw_data[ptr_offset:ptr_offset + 2] = cell_offset.to_bytes(2, 'big')
        self.cell_count += 1
        self.cell_pointers.insert(index, cell_offset)
        self._write_header()
        self.dirty = True
        return True

    def delete_cell(self, index: int):
        cell_data = self.read_cell(index)
        cell_offset = self.cell_pointers[index]
        cell_size = len(cell_data)
        self._add_freeblock(cell_offset, cell_size)
        for i in range(index, self.cell_count - 1):
            dst = self._pointer_offset(i)
            src = self._pointer_offset(i + 1)
            self.raw_data[dst:dst + 2] = self.raw_data[src:src + 2]
        self.cell_count -= 1
        self.cell_pointers.pop(index)
        self._write_header()
        self.dirty = True

    def _pointer_offset(self, index: int) -> int:
        header_size = 12 if self.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX) else 8
        return self.b_tree_offset + header_size + (index * 2)

    def _allocate_space(self, size: int) -> int:
        offset = self._freeblock_alloc(size)
        if offset != 0:
            return offset
        old_offset = self.cell_content_offset
        new_offset = old_offset - size
        if new_offset < self._pointer_offset(self.cell_count):
            self._defragment()
            old_offset2 = self.cell_content_offset
            new_offset2 = old_offset2 - size
            if new_offset2 < self._pointer_offset(self.cell_count):
                return -1  # page full
            self.cell_content_offset = new_offset2
            self._write_header()
            self.dirty = True
            return new_offset2
        self.cell_content_offset = new_offset
        self._write_header()
        self.dirty = True
        return new_offset

    def _freeblock_alloc(self, size: int) -> int:
        prev = 0
        current = self.first_freeblock
        while current != 0:
            block_size = int.from_bytes(self.raw_data[current + 2:current + 4], 'big')
            if block_size >= size:
                if block_size - size >= 4:
                    remaining = block_size - size
                    new_off = current + size
                    self.raw_data[new_off:new_off + 2] = self.raw_data[current:current + 2]
                    self.raw_data[new_off + 2:new_off + 4] = remaining.to_bytes(2, 'big')
                    if prev == 0:
                        self.first_freeblock = new_off
                    else:
                        self.raw_data[prev:prev + 2] = new_off.to_bytes(2, 'big')
                else:
                    if prev == 0:
                        self.first_freeblock = int.from_bytes(
                            self.raw_data[current:current + 2], 'big'
                        )
                    else:
                        self.raw_data[prev:prev + 2] = self.raw_data[current:current + 2]
                self._write_header()
                self.dirty = True
                return current
            prev = current
            next_off = int.from_bytes(self.raw_data[current:current + 2], 'big')
            current = next_off
        return 0

    def _add_freeblock(self, offset: int, size: int):
        self.raw_data[offset:offset + 2] = self.first_freeblock.to_bytes(2, 'big')
        self.raw_data[offset + 2:offset + 4] = size.to_bytes(2, 'big')
        self.first_freeblock = offset
        if size < 4:
            self.fragmented_free_bytes += size
        self._write_header()
        self.dirty = True

    def _needs_defrag(self) -> bool:
        return self.fragmented_free_bytes > (self.cell_content_offset * 0.1)

    def _defragment(self):
        cells = [self.read_cell(i) for i in range(self.cell_count)]
        new_content_end = self.pager.page_size
        for i, cell_data in enumerate(cells):
            size = len(cell_data)
            new_offset = new_content_end - size
            self.raw_data[new_offset:new_offset + size] = cell_data
            self.cell_pointers[i] = new_offset
            new_content_end = new_offset
        for i in range(self.cell_count):
            ptr_offset = self._pointer_offset(i)
            self.raw_data[ptr_offset:ptr_offset + 2] = self.cell_pointers[i].to_bytes(2, 'big')
        self.first_freeblock = 0
        self.fragmented_free_bytes = 0
        self.cell_content_offset = new_content_end
        self._write_header()
        self.dirty = True

    def _max_local_payload(self) -> int:
        """Maximum bytes of payload stored inline before overflow is needed."""
        usable = self.pager.page_size
        max_local = ((usable - 4) * MAX_EMBEDDED_PAYLOAD_FRACTION) // 100 - 4
        min_local = ((usable - 4) * LEAF_PAYLOAD_FRACTION) // 100 - 4
        return max(max_local, min_local)

    def _read_overflow_chain(self, first_page: int, total_size: int) -> bytes:
        """Read chained overflow pages. Returns concatenated overflow data."""
        data = bytearray()
        remaining = total_size
        page_num = first_page
        usable = self.pager.page_size
        while page_num != 0 and remaining > 0:
            pg_data = self.pager.read_page(page_num)
            next_page = int.from_bytes(pg_data[0:4], 'big')
            chunk_size = min(remaining, usable - 4)
            data.extend(pg_data[4:4 + chunk_size])
            remaining -= chunk_size
            page_num = next_page
        return bytes(data)

    def _write_overflow_chain(self, data: bytes) -> int:
        """Write data to chained overflow pages. Returns first page number."""
        usable = self.pager.page_size
        chunk_size = usable - 4
        first_page = 0
        prev_page = 0
        offset = 0
        while offset < len(data):
            chunk = data[offset:offset + chunk_size]
            page_num = self.pager.allocate_page()
            pg_data = bytearray(usable)
            pg_data[0:4] = (0).to_bytes(4, 'big')
            pg_data[4:4 + len(chunk)] = chunk
            self.pager.write_page(page_num, bytes(pg_data))
            if prev_page != 0:
                prev_data = bytearray(self.pager.read_page(prev_page))
                prev_data[0:4] = page_num.to_bytes(4, 'big')
                self.pager.write_page(prev_page, bytes(prev_data))
            if first_page == 0:
                first_page = page_num
            prev_page = page_num
            offset += chunk_size
        return first_page

    def read_full_payload(self, index: int) -> bytes:
        """Read cell's full payload at index, following overflow chain if needed."""
        raw = self.read_cell(index)
        offset = 0
        payload_length, consumed = decode_varint(raw, offset)
        offset += consumed
        if self.page_type in (PT_LEAF_TABLE, PT_INTERIOR_TABLE):
            rowid, consumed = decode_varint(raw, offset)
            offset += consumed
        max_local = self._max_local_payload()
        if payload_length <= max_local:
            return bytes(raw[offset:offset + payload_length])
        inline_size = max_local
        inline_data = raw[offset:offset + inline_size]
        overflow_page = int.from_bytes(raw[offset + inline_size:offset + inline_size + 4], 'big')
        overflow_data = self._read_overflow_chain(overflow_page, payload_length - inline_size)
        return bytes(inline_data + overflow_data)

    def _make_leaf_cell_data(self, rowid: int, payload: bytes) -> bytes:
        """Create leaf table cell bytes, splitting payload into overflow if needed."""
        max_local = self._max_local_payload()
        if len(payload) <= max_local:
            return TableLeafCell(rowid, payload).serialize()
        inline_payload = payload[:max_local]
        overflow_data = payload[max_local:]
        first_overflow = self._write_overflow_chain(overflow_data)
        buf = bytearray()
        buf.extend(encode_varint(len(payload)))
        buf.extend(encode_varint(rowid))
        buf.extend(inline_payload)
        buf.extend(first_overflow.to_bytes(4, 'big'))
        return bytes(buf)

    def flush(self):
        self._write_header()
        self.pager.write_page(self.page_number, bytes(self.raw_data))
        self.dirty = False

    def is_leaf(self) -> bool:
        return self.page_type in (PT_LEAF_TABLE, PT_LEAF_INDEX)

    def is_table(self) -> bool:
        return self.page_type in (PT_LEAF_TABLE, PT_INTERIOR_TABLE)


class BTreeCursor:
    """Cursor for navigating a B-Tree. Tracks position per level on a stack."""

    def __init__(self, btree: 'BTree', root_page: int):
        self.btree = btree
        self.root_page = root_page
        self.stack: list[tuple[int, int]] = []
        self.eof = False
        self.bof = True

    def first(self):
        """Position cursor at the first (leftmost) entry."""
        self.stack = []
        page_num = self.btree.root_page
        page = BTreePage(self.btree.pager, page_num)

        while page.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX):
            if page.cell_count == 0:
                self.stack.append((page_num, 0))
                page_num = page.right_child
            else:
                cell_data = page.read_cell(0)
                if page.page_type == PT_INTERIOR_TABLE:
                    cell = TableInteriorCell.parse(cell_data)
                else:
                    cell = IndexInteriorCell.parse(cell_data)
                self.stack.append((page_num, 0))
                page_num = cell.left_child_page
            page = BTreePage(self.btree.pager, page_num)

        if page.cell_count == 0:
            self.eof = True
            return
        self.stack.append((page.page_number, 0))
        self.eof = False
        self.bof = False

    def last(self):
        """Position cursor at the last (rightmost) entry."""
        self.stack = []
        page_num = self.btree.root_page
        page = BTreePage(self.btree.pager, page_num)

        while page.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX):
            if page.cell_count > 0:
                self.stack.append((page_num, page.cell_count - 1))
                cell_data = page.read_cell(page.cell_count - 1)
                if page.page_type == PT_INTERIOR_TABLE:
                    cell = TableInteriorCell.parse(cell_data)
                    page_num = cell.left_child_page
                else:
                    cell = IndexInteriorCell.parse(cell_data)
                    page_num = cell.left_child_page
            else:
                if page.right_child == 0:
                    self.eof = True
                    return
                self.stack.append((page_num, 0))
                page_num = page.right_child
            page = BTreePage(self.btree.pager, page_num)

        if page.cell_count == 0:
            self.eof = True
            return
        self.stack.append((page.page_number, page.cell_count - 1))
        self.eof = False
        self.bof = False

    def next(self):
        """Advance cursor to next entry in key order."""
        if self.eof:
            return

        page_num, cell_idx = self.stack.pop()
        page = BTreePage(self.btree.pager, page_num)

        if cell_idx + 1 < page.cell_count:
            self.stack.append((page_num, cell_idx + 1))
            if not page.is_leaf():
                self._descend_to_leftmost_leaf()
            return

        while self.stack:
            parent_num, parent_idx = self.stack.pop()
            parent = BTreePage(self.btree.pager, parent_num)

            if parent_idx < parent.cell_count:
                next_idx = parent_idx + 1
                if next_idx < parent.cell_count:
                    cell_data = parent.read_cell(next_idx)
                    if parent.page_type == PT_INTERIOR_TABLE:
                        cell = TableInteriorCell.parse(cell_data)
                    else:
                        cell = IndexInteriorCell.parse(cell_data)
                    next_page = cell.left_child_page
                    self.stack.append((parent_num, next_idx))
                else:
                    next_page = parent.right_child
                    self.stack.append((parent_num, parent.cell_count))
                self._descend_to_leftmost_leaf_from(next_page)
                return

        self.eof = True

    def _descend_to_leftmost_leaf(self):
        page_num, _ = self.stack[-1]
        page = BTreePage(self.btree.pager, page_num)
        while not page.is_leaf():
            if page.cell_count == 0:
                page_num = page.right_child
            else:
                cell_data = page.read_cell(0)
                if page.page_type == PT_INTERIOR_TABLE:
                    cell = TableInteriorCell.parse(cell_data)
                else:
                    cell = IndexInteriorCell.parse(cell_data)
                page_num = cell.left_child_page
            self.stack.append((page_num, 0))
            page = BTreePage(self.btree.pager, page_num)

    def _descend_to_leftmost_leaf_from(self, page_num: int):
        while True:
            pg = BTreePage(self.btree.pager, page_num)
            if pg.is_leaf():
                self.stack.append((page_num, 0))
                return
            if pg.cell_count > 0:
                cell_data = pg.read_cell(0)
                if pg.page_type == PT_INTERIOR_TABLE:
                    cell = TableInteriorCell.parse(cell_data)
                else:
                    cell = IndexInteriorCell.parse(cell_data)
                self.stack.append((page_num, 0))
                page_num = cell.left_child_page
            else:
                self.stack.append((page_num, 0))
                page_num = pg.right_child

    def prev(self):
        """Move cursor to previous entry in key order."""
        if self.bof or not self.stack:
            return

        page_num, cell_idx = self.stack.pop()
        page = BTreePage(self.btree.pager, page_num)

        if cell_idx > 0:
            self.stack.append((page_num, cell_idx - 1))
            if not page.is_leaf():
                self._descend_to_rightmost_leaf()
            return

        while self.stack:
            parent_num, parent_idx = self.stack.pop()
            if parent_idx > 0:
                self.stack.append((parent_num, parent_idx - 1))
                if not page.is_leaf():
                    self._descend_to_rightmost_leaf()
                return

        self.bof = True

    def _descend_to_rightmost_leaf(self):
        page_num, _ = self.stack[-1]
        page = BTreePage(self.btree.pager, page_num)
        while not page.is_leaf():
            if page.cell_count > 0:
                cell_data = page.read_cell(page.cell_count - 1)
                if page.page_type == PT_INTERIOR_TABLE:
                    cell = TableInteriorCell.parse(cell_data)
                    page_num = cell.left_child_page
                else:
                    cell = IndexInteriorCell.parse(cell_data)
                    page_num = cell.left_child_page
            else:
                page_num = page.right_child
            self.stack.append((page_num, page.cell_count - 1 if page.cell_count > 0 else 0))
            page = BTreePage(self.btree.pager, page_num)

    def seek(self, key: int) -> bool:
        """
        Position cursor on the first entry >= key.
        Returns True if exact match found.
        """
        self.stack = []
        page_num = self.btree.root_page
        exact_match = False

        while True:
            page = BTreePage(self.btree.pager, page_num)

            if page.is_leaf():
                lo, hi = 0, page.cell_count - 1
                found_idx = -1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    cell_data = page.read_cell(mid)
                    if page.page_type == PT_LEAF_TABLE:
                        cell = TableLeafCell.parse(cell_data)
                        cell_key = cell.rowid
                    else:
                        rec, _ = Record.decode(cell_data)
                        cell_key = rec.get_values()[0]

                    if cell_key < key:
                        lo = mid + 1
                    elif cell_key > key:
                        hi = mid - 1
                    else:
                        found_idx = mid
                        exact_match = True
                        break

                if found_idx == -1:
                    found_idx = lo

                if found_idx >= page.cell_count:
                    self.eof = True
                else:
                    self.stack.append((page_num, found_idx))
                    self.eof = False
                return exact_match

            else:
                lo, hi = 0, page.cell_count - 1
                child = page.right_child
                found = False

                while lo <= hi:
                    mid = (lo + hi) // 2
                    cell_data = page.read_cell(mid)
                    if page.page_type == PT_INTERIOR_TABLE:
                        cell = TableInteriorCell.parse(cell_data)
                        cell_key = cell.key
                    else:
                        cell = IndexInteriorCell.parse(cell_data)
                        rec, _ = Record.decode(cell.payload)
                        cell_key = rec.get_values()[0]

                    if cell_key < key:
                        lo = mid + 1
                        child = page.right_child if mid + 1 >= page.cell_count else \
                            TableInteriorCell.parse(page.read_cell(mid + 1)).left_child_page
                    elif cell_key > key:
                        hi = mid - 1
                        child = cell.left_child_page
                    else:
                        child = cell.left_child_page
                        self.stack.append((page_num, mid))
                        found = True
                        exact_match = True
                        break

                if not found:
                    if lo < page.cell_count:
                        cell_data = page.read_cell(lo)
                        if page.page_type == PT_INTERIOR_TABLE:
                            child = TableInteriorCell.parse(cell_data).left_child_page
                        else:
                            child = IndexInteriorCell.parse(cell_data).left_child_page
                        self.stack.append((page_num, lo))
                    else:
                        self.stack.append((page_num, page.cell_count))
                    page_num = child
                else:
                    page_num = child

    def current_key(self) -> int:
        """Return the key (rowid for table, first column for index) at current position."""
        if not self.stack:
            raise CorruptError("Cursor not positioned")
        page_num, cell_idx = self.stack[-1]
        page = BTreePage(self.btree.pager, page_num)
        cell_data = page.read_cell(cell_idx)

        if page.page_type == PT_LEAF_TABLE:
            cell = TableLeafCell.parse(cell_data)
            return cell.rowid
        elif page.page_type == PT_LEAF_INDEX:
            cell = IndexLeafCell.parse(cell_data)
            rec, _ = Record.decode(cell.payload)
            return rec.get_values()[0]
        elif page.page_type == PT_INTERIOR_TABLE:
            cell = TableInteriorCell.parse(cell_data)
            return cell.key
        else:
            cell = IndexInteriorCell.parse(cell_data)
            rec, _ = Record.decode(cell.payload)
            return rec.get_values()[0]

    def current_payload(self) -> bytes:
        """Return the full payload at current position (table leaf only)."""
        if not self.stack:
            raise CorruptError("Cursor not positioned")
        page_num, cell_idx = self.stack[-1]
        page = BTreePage(self.btree.pager, page_num)
        return page.read_full_payload(cell_idx)

    def insert(self, key: int, rowid: int, payload: bytes):
        """Insert a new entry into the B-Tree."""
        page_num = self.btree.root_page
        page = BTreePage(self.btree.pager, page_num)

        path = []
        while not page.is_leaf():
            inserted = False
            for i in range(page.cell_count):
                data = page.read_cell(i)
                if page.page_type == PT_INTERIOR_TABLE:
                    cell = TableInteriorCell.parse(data)
                    if key < cell.key:
                        path.append((page_num, i))
                        page_num = cell.left_child_page
                        inserted = True
                        break
                else:
                    cell = IndexInteriorCell.parse(data)
                    rec, _ = Record.decode(cell.payload)
                    ck = rec.get_values()[0]
                    if key < ck:
                        path.append((page_num, i))
                        page_num = cell.left_child_page
                        inserted = True
                        break
            if not inserted:
                path.append((page_num, page.cell_count))
                page_num = page.right_child
            page = BTreePage(self.btree.pager, page_num)

        if page.page_type == PT_LEAF_TABLE:
            cell_data = page._make_leaf_cell_data(rowid, payload)
        else:
            cell_data = IndexLeafCell(payload).serialize()

        insert_idx = 0
        for i in range(page.cell_count):
            cdata = page.read_cell(i)
            if page.page_type == PT_LEAF_TABLE:
                ccell = TableLeafCell.parse(cdata)
                ck = ccell.rowid
            else:
                ccell = IndexLeafCell.parse(cdata)
                rec, _ = Record.decode(ccell.payload)
                ck = rec.get_values()[0]
            if ck < key:
                insert_idx = i + 1

        if not page.insert_cell(insert_idx, cell_data):
            self._balance(path, page, insert_idx, extra_cell=cell_data)
            return
        leaf_page = page

        leaf_page.flush()
        space_left = leaf_page.cell_content_offset - leaf_page._pointer_offset(leaf_page.cell_count)
        if space_left < 120:
            self._balance(path, leaf_page, insert_idx)

    def _balance(self, path: list, page: BTreePage, insert_idx: int,
                  extra_cell: bytes | None = None):
        """Split a full leaf page and cascade splits upward."""
        entries = []
        for i in range(page.cell_count):
            cell_data = page.read_cell(i)
            if page.page_type == PT_LEAF_TABLE:
                cell = TableLeafCell.parse(cell_data)
                entries.append((cell.rowid, cell_data))
            else:
                cell = IndexLeafCell.parse(cell_data)
                rec, _ = Record.decode(cell.payload)
                key = rec.get_values()[0]
                entries.append((key, cell_data))

        if extra_cell is not None:
            if page.page_type == PT_LEAF_TABLE:
                cell = TableLeafCell.parse(extra_cell)
                entries.append((cell.rowid, extra_cell))
            else:
                cell = IndexLeafCell.parse(extra_cell)
                rec, _ = Record.decode(cell.payload)
                key = rec.get_values()[0]
                entries.append((key, extra_cell))

        entries.sort(key=lambda x: x[0])
        mid = len(entries) // 2
        middle_key = entries[mid][0]
        middle_data = entries[mid][1]

        new_page_num = self.btree.create_leaf_page()
        new_page = BTreePage(self.btree.pager, new_page_num)

        page.cell_count = 0
        page.cell_content_offset = self.btree.pager.page_size
        page._write_header()
        page.dirty = True
        page.cell_pointers.clear()

        for i, (key, data) in enumerate(entries):
            if i < mid:
                page.insert_cell(page.cell_count, data)
            else:
                new_page.insert_cell(new_page.cell_count, data)

        page.flush()
        new_page.flush()

        if not path:
            new_root = self.btree.create_interior_page(new_page.page_number)
            new_root_page = BTreePage(self.btree.pager, new_root)
            promoted_data = middle_data if page.page_type == PT_LEAF_TABLE else middle_data
            if page.page_type == PT_LEAF_TABLE:
                middle_cell = TableLeafCell.parse(middle_data)
                promoted_cell = TableInteriorCell(page.page_number, middle_cell.rowid)
            else:
                promoted_cell = IndexInteriorCell(page.page_number, middle_data)
            new_root_page.insert_cell(0, promoted_cell.serialize())
            new_root_page.right_child = new_page.page_number
            new_root_page.flush()
            self.btree.root_page = new_root
        else:
            self._promote_to_parent(path, middle_data, new_page_num, page.page_number, page.is_table())

    def _promote_to_parent(self, path: list, middle_data: bytes,
                           new_page_num: int, old_page_num: int, is_table: bool):
        """Promote the middle entry to the parent page."""
        parent_num, parent_idx = path.pop()
        parent = BTreePage(self.btree.pager, parent_num)

        if is_table:
            middle_cell = TableLeafCell.parse(middle_data)
            promoted = TableInteriorCell(old_page_num, middle_cell.rowid)
        else:
            promoted = IndexInteriorCell(old_page_num, middle_data)

        parent.insert_cell(parent_idx, promoted.serialize())
        parent.right_child = new_page_num
        parent.flush()

    def delete(self):
        """Delete the entry at current cursor position."""
        if not self.stack or self.eof:
            return
        page_num, cell_idx = self.stack[-1]
        page = BTreePage(self.btree.pager, page_num)
        page.delete_cell(cell_idx)
        page.flush()

        if page.cell_count == 0:
            if page.page_number != self.btree.root_page:
                self._rebalance_after_delete()
            else:
                self.stack.clear()
                self.eof = True
                self.bof = True

    def _rebalance_after_delete(self):
        """Free the now-empty page and remove reference from parent. Cascades upward."""
        while len(self.stack) >= 2:
            empty_page_num, _ = self.stack.pop()
            parent_num, _ = self.stack[-1]
            parent = BTreePage(self.btree.pager, parent_num)

            removed = False
            for i in range(parent.cell_count):
                data = parent.read_cell(i)
                if parent.page_type == PT_INTERIOR_TABLE:
                    child = TableInteriorCell.parse(data).left_child_page
                else:
                    child = IndexInteriorCell.parse(data).left_child_page
                if child == empty_page_num:
                    parent.delete_cell(i)
                    removed = True
                    break

            if not removed and parent.right_child == empty_page_num:
                parent.right_child = 0
                parent._write_header()
                parent.dirty = True
                removed = True

            self.btree.pager.free_page(empty_page_num)
            parent.flush()

            if parent.cell_count > 0 or parent_num == self.btree.root_page:
                break
            # parent is empty and not root, continue cascading upward

        # If the root is interior with 0 cells after rebalance, convert to leaf
        root = BTreePage(self.btree.pager, self.btree.root_page)
        if root.cell_count == 0 and not root.is_leaf():
            root.page_type = PT_LEAF_TABLE if self.btree.is_table else PT_LEAF_INDEX
            root.right_child = 0
            root._write_header()
            root.dirty = True
            root.flush()

        self.stack.clear()
        self.eof = True
        self.bof = True

    def close(self):
        """Flush current page and reset cursor state."""
        if self.stack:
            page_num, _ = self.stack[-1]
            page = BTreePage(self.btree.pager, page_num)
            page.flush()
        self.stack = []
        self.eof = True
        self.bof = True


class BTree:
    """Manages a B-Tree structure with factory methods for cursors and pages."""

    def __init__(self, pager: 'Pager', root_page: int, is_table: bool = True):
        self.pager = pager
        self.root_page = root_page
        self.is_table = is_table

    def cursor(self) -> BTreeCursor:
        return BTreeCursor(self, self.root_page)

    def create_leaf_page(self) -> int:
        """Create a new empty leaf page."""
        page_num = self.pager.allocate_page()
        page = BTreePage(self.pager, page_num)
        page.page_type = PT_LEAF_TABLE if self.is_table else PT_LEAF_INDEX
        page.cell_count = 0
        page.first_freeblock = 0
        page.cell_content_offset = self.pager.page_size
        page.fragmented_free_bytes = 0
        page.right_child = 0
        page.flush()
        return page_num

    def create_interior_page(self, right_child: int) -> int:
        """Create a new interior page with given rightmost child."""
        page_num = self.pager.allocate_page()
        page = BTreePage(self.pager, page_num)
        page.page_type = PT_INTERIOR_TABLE if self.is_table else PT_INTERIOR_INDEX
        page.cell_count = 0
        page.first_freeblock = 0
        page.cell_content_offset = self.pager.page_size
        page.fragmented_free_bytes = 0
        page.right_child = right_child
        page.flush()
        return page_num

    def split_leaf_page(self, page: BTreePage) -> tuple[int, int, bytes]:
        """Split a full leaf page. Returns (new_page_num, middle_key, middle_payload)."""
        entries = []
        for i in range(page.cell_count):
            cell_data = page.read_cell(i)
            if page.page_type == PT_LEAF_TABLE:
                cell = TableLeafCell.parse(cell_data)
                entries.append((cell.rowid, cell_data))
            else:
                cell = IndexLeafCell.parse(cell_data)
                rec, _ = Record.decode(cell.payload)
                key = rec.get_values()[0]
                entries.append((key, cell_data))

        entries.sort(key=lambda x: x[0])
        mid = len(entries) // 2
        middle_key = entries[mid][0]
        middle_payload = entries[mid][1]

        new_page_num = self.create_leaf_page()
        new_page = BTreePage(self.pager, new_page_num)

        page.cell_count = 0
        page.cell_content_offset = self.btree.pager.page_size
        page._write_header()
        page.dirty = True

        for i, (key, data) in enumerate(entries):
            if i < mid:
                page.insert_cell(page.cell_count, data)
            else:
                new_page.insert_cell(new_page.cell_count, data)

        page.flush()
        new_page.flush()

        return (new_page_num, middle_key, middle_payload)
