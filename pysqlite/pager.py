"""Pager — page cache, ACID rollback journal, freelist management."""

import dataclasses
from .vfs import VFS, FileHandle
from .constants import (
    HEADER_SIZE, HEADER_MAGIC, DEFAULT_PAGE_SIZE, MIN_PAGE_SIZE, MAX_PAGE_SIZE,
    MAX_EMBEDDED_PAYLOAD_FRACTION, MIN_EMBEDDED_PAYLOAD_FRACTION,
    LEAF_PAYLOAD_FRACTION, ENCODING_UTF8,
    LOCK_NONE, LOCK_SHARED, LOCK_RESERVED, LOCK_EXCLUSIVE,
    SQLITE_OPEN_READWRITE, SQLITE_OPEN_CREATE, SQLITE_OPEN_READONLY,
    SYNC_NORMAL, SYNC_FULL,
    JOURNAL_MAGIC, JOURNAL_HEADER_SIZE,
    JournalMode,
)
from .errors import (
    NotADbError, CorruptError, MisuseError, BusyError,
)


@dataclasses.dataclass
class DatabaseHeader:
    """Parsed fields from the 100-byte database header (page 1)."""
    page_size: int = DEFAULT_PAGE_SIZE
    write_format: int = 1
    read_format: int = 1
    reserved_space: int = 0
    file_change_counter: int = 1
    database_size: int = 1
    freelist_trunk: int = 0
    freelist_count: int = 0
    schema_cookie: int = 1
    schema_format: int = 4
    default_cache_size: int = 0
    largest_root_page: int = 0
    text_encoding: int = ENCODING_UTF8
    user_version: int = 0
    incremental_vacuum: int = 0
    application_id: int = 0
    version_valid_for: int = 0
    sqlite_version: int = 3040000


class Page:
    """A single database page with mutable bytearray data."""

    def __init__(self, number: int, data: bytes, dirty: bool = False):
        self.number = number
        self.data = bytearray(data)
        self.dirty = dirty


class Pager:
    """Manages the database as an array of fixed-size pages.

    Provides page-level read/write, ACID via rollback journal,
    page caching with LRU eviction, and freelist management.
    """

    def __init__(self, vfs: VFS, path: str, flags: int = SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE):
        self.vfs = vfs
        self.handle = vfs.open(path, flags)
        self.page_size = DEFAULT_PAGE_SIZE
        self.total_pages = 0
        self.cache: dict[int, Page] = {}
        self.dirty_pages: set[int] = set()
        self.ref_count: dict[int, int] = {}
        self.freelist_trunk: int = 0
        self.freelist_count: int = 0
        self.db_header: DatabaseHeader | None = None
        self.in_transaction: bool = False
        self.journal_fd: FileHandle | None = None
        self.journal_mode: str = JournalMode.DELETE
        self.schema_version: int = 0
        self.schema_cookie: int = 0
        self.file_change_counter: int = 0
        self._before_images: dict[int, bytes] = {}
        self._access_time: dict[int, int] = {}
        self._clock: int = 0

        self._open_db()

    # ---- initialization ----

    def _open_db(self):
        """Open an existing database or create a new one."""
        if self.vfs.file_size(self.handle) == 0:
            self._init_header()
            self.total_pages = 1
            self.file_change_counter = self.db_header.file_change_counter
            self.schema_cookie = self.db_header.schema_cookie
            self.vfs.sync(self.handle, SYNC_FULL)
        else:
            header_raw = self.vfs.read(self.handle, 0, HEADER_SIZE)
            self._parse_header(header_raw)
            self.total_pages = self.db_header.database_size
            if self._hot_journal_exists():
                self._recover_hot_journal()

    def _init_header(self):
        """Write a default database header for a new database."""
        buf = bytearray(HEADER_SIZE)
        buf[0:16] = HEADER_MAGIC
        buf[16:18] = self.page_size.to_bytes(2, 'big')
        buf[18] = 1
        buf[19] = 1
        buf[20] = 0
        buf[21] = MAX_EMBEDDED_PAYLOAD_FRACTION
        buf[22] = MIN_EMBEDDED_PAYLOAD_FRACTION
        buf[23] = LEAF_PAYLOAD_FRACTION
        buf[24:28] = (1).to_bytes(4, 'big')
        buf[28:32] = (1).to_bytes(4, 'big')
        buf[40:44] = (1).to_bytes(4, 'big')
        buf[44:48] = (4).to_bytes(4, 'big')
        buf[56:60] = ENCODING_UTF8.to_bytes(4, 'big')
        buf[96:100] = (3040000).to_bytes(4, 'big')
        self.vfs.write(self.handle, 0, bytes(buf))
        self.db_header = DatabaseHeader()

    def _parse_header(self, data: bytes):
        """Parse the 100-byte database header."""
        if data[0:16] != HEADER_MAGIC:
            raise NotADbError("Not a SQLite database")

        page_size = int.from_bytes(data[16:18], 'big')
        if page_size == 1:
            page_size = 65536
        if page_size < MIN_PAGE_SIZE or page_size > MAX_PAGE_SIZE:
            raise CorruptError(f"Invalid page size: {page_size}")
        if page_size & (page_size - 1) != 0:
            raise CorruptError(f"Page size not power of 2: {page_size}")
        self.page_size = page_size

        self.db_header = DatabaseHeader(
            page_size=page_size,
            write_format=data[18],
            read_format=data[19],
            reserved_space=data[20],
            file_change_counter=int.from_bytes(data[24:28], 'big'),
            database_size=int.from_bytes(data[28:32], 'big'),
            freelist_trunk=int.from_bytes(data[32:36], 'big'),
            freelist_count=int.from_bytes(data[36:40], 'big'),
            schema_cookie=int.from_bytes(data[40:44], 'big'),
            schema_format=int.from_bytes(data[44:48], 'big'),
            default_cache_size=int.from_bytes(data[48:52], 'big'),
            largest_root_page=int.from_bytes(data[52:56], 'big'),
            text_encoding=int.from_bytes(data[56:60], 'big'),
            user_version=int.from_bytes(data[60:64], 'big'),
            incremental_vacuum=int.from_bytes(data[64:68], 'big'),
            application_id=int.from_bytes(data[68:72], 'big'),
            version_valid_for=int.from_bytes(data[92:96], 'big'),
            sqlite_version=int.from_bytes(data[96:100], 'big'),
        )
        self.freelist_trunk = self.db_header.freelist_trunk
        self.freelist_count = self.db_header.freelist_count
        self.file_change_counter = self.db_header.file_change_counter
        self.schema_cookie = self.db_header.schema_cookie

    def _write_header_field(self, offset: int, data: bytes):
        """Write a single field in the database header (page 1)."""
        page1 = self.read_page(1)
        page1[offset:offset + len(data)] = data
        self.write_page(1, bytes(page1))
        self.flush()

    def _update_freelist_headers(self):
        """Sync freelist trunk and count back to the database header."""
        buf = self.freelist_trunk.to_bytes(4, 'big')
        self._write_header_field(32, buf)
        buf = self.freelist_count.to_bytes(4, 'big')
        self._write_header_field(36, buf)
        if self.db_header is not None:
            self.db_header.freelist_trunk = self.freelist_trunk
            self.db_header.freelist_count = self.freelist_count

    # ---- page read / write ----

    def read_page(self, page_number: int) -> bytearray:
        """Read a page from cache or disk. Returns mutable bytearray."""
        if page_number < 1 or page_number > self.total_pages:
            raise CorruptError(f"Page {page_number} out of range (total: {self.total_pages})")

        if page_number in self.cache:
            self._accessed(page_number)
            return self.cache[page_number].data

        offset = (page_number - 1) * self.page_size
        data = self.vfs.read(self.handle, offset, self.page_size)
        page = Page(page_number, data)
        self.cache[page_number] = page
        self._accessed(page_number)
        return page.data

    def write_page(self, page_number: int, data: bytes):
        """Mark a page as dirty (will be written to disk on flush).

        If in a transaction, the before-image is automatically journaled
        before the first modification to each page.
        """
        if self.in_transaction:
            self._journal_page(page_number)
        if page_number not in self.cache:
            page = Page(page_number, data)
            self.cache[page_number] = page
        else:
            self.cache[page_number].data = bytearray(data)
        self.cache[page_number].dirty = True
        self.dirty_pages.add(page_number)

    def pin_page(self, page_number: int):
        """Pin a page in cache so it won't be evicted."""
        self.ref_count[page_number] = self.ref_count.get(page_number, 0) + 1

    def unpin_page(self, page_number: int):
        """Release a pinned page."""
        self.ref_count[page_number] -= 1
        if self.ref_count[page_number] <= 0:
            del self.ref_count[page_number]

    def flush(self):
        """Write all dirty pages to disk."""
        for page_num in sorted(self.dirty_pages):
            page = self.cache[page_num]
            offset = (page_num - 1) * self.page_size
            self.vfs.write(self.handle, offset, bytes(page.data))
            page.dirty = False
        self.dirty_pages.clear()

    def sync(self):
        """Flush + fsync."""
        self.flush()
        self.vfs.sync(self.handle, SYNC_FULL)

    def _evict_page(self):
        """Evict the least-recently-used unpinned page from cache."""
        candidates = [p for p in self.cache if self.ref_count.get(p, 0) == 0]
        if not candidates:
            return
        oldest = min(candidates, key=lambda p: self._access_time.get(p, 0))
        del self.cache[oldest]
        self._access_time.pop(oldest, None)

    def _accessed(self, page_number: int):
        """Record that a page was accessed (for LRU)."""
        self._access_time[page_number] = self._clock
        self._clock += 1

    # ---- rollback journal ----

    def begin_transaction(self, exclusive: bool = False):
        """Begin a transaction. Saves before-images in the journal."""
        if self.in_transaction:
            raise MisuseError("Already in a transaction")

        if self.journal_mode == JournalMode.OFF:
            self.in_transaction = True
            return

        journal_path = self.handle.path + "-journal"
        journal_flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE
        self.journal_fd = self.vfs.open(journal_path, journal_flags)

        lock = LOCK_EXCLUSIVE if exclusive else LOCK_RESERVED
        if not self.vfs.lock(self.handle, lock):
            self.vfs.close(self.journal_fd)
            self.journal_fd = None
            raise BusyError("Database is locked")

        self._write_journal_header(0)
        self.vfs.sync(self.journal_fd, SYNC_NORMAL)

        self.in_transaction = True
        self._before_images = {}

    def _journal_page(self, page_number: int):
        """Save the original page content to journal before first modification."""
        if page_number in self._before_images:
            return

        offset = (page_number - 1) * self.page_size
        original = self.vfs.read(self.handle, offset, self.page_size)
        self._before_images[page_number] = original
        self._write_journal_page(page_number, original)

    def _write_journal_header(self, n_pages: int):
        """Write a 28-byte journal header."""
        buf = bytearray(JOURNAL_HEADER_SIZE)
        buf[0:4] = (0xd9d505f9).to_bytes(4, 'big')
        buf[4:8] = self.total_pages.to_bytes(4, 'big')
        buf[8:12] = self.page_size.to_bytes(4, 'big')
        buf[12:16] = n_pages.to_bytes(4, 'big')
        checksum = 0
        for i in range(16):
            checksum ^= buf[i]
        buf[16:20] = checksum.to_bytes(4, 'big')
        buf[20:24] = (1).to_bytes(4, 'big')  # first page number
        self.vfs.write(self.journal_fd, 0, bytes(buf))

    def _write_journal_page(self, page_number: int, data: bytes):
        """Append a page's original content to the journal."""
        if self.journal_mode == JournalMode.MEMORY:
            return
        j_size = self.vfs.file_size(self.journal_fd)
        self.vfs.write(self.journal_fd, j_size, data)

    def _finalize_journal(self):
        """Mark journal as committed by setting nPages to 0."""
        if self.journal_fd is None:
            return
        buf = (0).to_bytes(4, 'big')
        self.vfs.write(self.journal_fd, 12, buf)
        self.vfs.sync(self.journal_fd, SYNC_FULL)

    def _zero_journal_header(self):
        """Zero out the journal header to mark it invalid."""
        if self.journal_fd is None:
            return
        self.vfs.write(self.journal_fd, 0, b'\x00' * JOURNAL_HEADER_SIZE)

    def commit_transaction(self):
        """Commit all changes atomically."""
        if not self.in_transaction:
            return

        try:
            self.flush()
            self.vfs.sync(self.handle, SYNC_FULL)
            self._finalize_journal()

            if self.journal_mode == JournalMode.DELETE:
                self.vfs.close(self.journal_fd)
                self.vfs.delete(self.handle.path + "-journal")
            elif self.journal_mode == JournalMode.TRUNCATE:
                self.vfs.truncate(self.journal_fd, 0)
                self.vfs.close(self.journal_fd)
            elif self.journal_mode == JournalMode.PERSIST:
                self._zero_journal_header()
                self.vfs.sync(self.journal_fd, SYNC_FULL)
                self.vfs.close(self.journal_fd)
            elif self.journal_mode == JournalMode.MEMORY:
                pass

            self.file_change_counter += 1
            self._write_header_field(24, self.file_change_counter.to_bytes(4, 'big'))

        except Exception:
            self._rollback_transaction()
            raise
        finally:
            self.in_transaction = False
            self._before_images = {}
            self.journal_fd = None
            self.vfs.unlock(self.handle, LOCK_SHARED)

    def rollback_transaction(self):
        """Restore database to state before the transaction began."""
        self._rollback_transaction()

    def _rollback_transaction(self):
        if not self.in_transaction:
            return
        try:
            for page_number, original in self._before_images.items():
                offset = (page_number - 1) * self.page_size
                self.vfs.write(self.handle, offset, original)
                if page_number in self.cache:
                    del self.cache[page_number]
            self.vfs.sync(self.handle, SYNC_FULL)
            if self.journal_fd is not None:
                self.vfs.close(self.journal_fd)
                self.vfs.delete(self.handle.path + "-journal")
        finally:
            self.in_transaction = False
            self._before_images = {}
            self.dirty_pages.clear()
            self.journal_fd = None
            self.vfs.unlock(self.handle, LOCK_SHARED)

    # ---- hot journal recovery ----

    def _hot_journal_exists(self) -> bool:
        """Check if a hot journal file needs recovery."""
        journal_path = self.handle.path + "-journal"
        if not self.vfs.file_exists(journal_path):
            return False
        try:
            jh = self.vfs.open(journal_path, SQLITE_OPEN_READONLY)
            header = self.vfs.read(jh, 0, 28)
            self.vfs.close(jh)
            if len(header) < 28:
                return False
            magic = int.from_bytes(header[0:4], 'big')
            if magic != 0xd9d505f9:
                return False
            n_pages = int.from_bytes(header[12:16], 'big')
            return n_pages > 0
        except Exception:
            return False

    def _recover_hot_journal(self):
        """Replay hot journal to restore database consistency."""
        journal_path = self.handle.path + "-journal"

        if not self.vfs.lock(self.handle, LOCK_EXCLUSIVE):
            raise BusyError("Cannot acquire lock for crash recovery")

        try:
            jh = self.vfs.open(journal_path, SQLITE_OPEN_READONLY)
            journal_size = self.vfs.file_size(jh)
            sector_size = self.vfs.sector_size(self.handle)

            offset = 0
            while offset < journal_size:
                header = self.vfs.read(jh, offset, 28)
                if len(header) < 28:
                    break

                magic = int.from_bytes(header[0:4], 'big')
                if magic != 0xd9d505f9:
                    break

                j_page_size = int.from_bytes(header[8:12], 'big')
                n_pages = int.from_bytes(header[12:16], 'big')
                first_page = int.from_bytes(header[20:24], 'big')

                if n_pages == 0:
                    break

                for i in range(n_pages):
                    page_offset = offset + 28 + (i * j_page_size)
                    page_data = self.vfs.read(jh, page_offset, j_page_size)
                    disk_offset = (first_page + i - 1) * self.page_size
                    self.vfs.write(self.handle, disk_offset, page_data)

                offset += sector_size

            self.vfs.close(jh)
            self.vfs.sync(self.handle, SYNC_FULL)
            self.vfs.delete(journal_path)
        finally:
            self.vfs.unlock(self.handle, LOCK_SHARED)

    # ---- freelist ----

    def allocate_page(self) -> int:
        """Allocate a new page from the freelist or extend the database."""
        if self.freelist_count > 0:
            page_num = self._pop_freelist()
            self.freelist_count -= 1
            self._update_freelist_headers()
        else:
            self.total_pages += 1
            page_num = self.total_pages
            self.db_header.database_size = self.total_pages
            self._write_header_field(28, self.total_pages.to_bytes(4, 'big'))

        self.write_page(page_num, b'\x00' * self.page_size)
        return page_num

    def free_page(self, page_number: int):
        """Add a page to the freelist for reuse."""
        self._push_freelist(page_number)
        self.freelist_count += 1
        self._update_freelist_headers()
        if page_number in self.cache:
            del self.cache[page_number]
        self.dirty_pages.discard(page_number)

    def _pop_freelist(self) -> int:
        """Remove and return a page from the freelist."""
        if self.freelist_trunk == 0:
            raise CorruptError("Freelist empty but count > 0")

        trunk_data = self.read_page(self.freelist_trunk)
        n_leaves = int.from_bytes(trunk_data[4:8], 'big')

        if n_leaves > 0:
            leaf_offset = 8 + ((n_leaves - 1) * 4)
            leaf_page = int.from_bytes(trunk_data[leaf_offset:leaf_offset + 4], 'big')
            trunk_data[4:8] = (n_leaves - 1).to_bytes(4, 'big')
            self.write_page(self.freelist_trunk, bytes(trunk_data))
            return leaf_page
        else:
            next_trunk = int.from_bytes(trunk_data[0:4], 'big')
            page = self.freelist_trunk
            self.freelist_trunk = next_trunk
            return page

    def _push_freelist(self, page_number: int):
        """Add a page to the freelist."""
        self.write_page(page_number, b'\x00' * self.page_size)

        if self.freelist_trunk == 0:
            self.freelist_trunk = page_number
            trunk_data = bytearray(self.page_size)
            trunk_data[0:4] = (0).to_bytes(4, 'big')
            trunk_data[4:8] = (0).to_bytes(4, 'big')
            self.write_page(page_number, bytes(trunk_data))
        else:
            trunk_data = self.read_page(self.freelist_trunk)
            n_leaves = int.from_bytes(trunk_data[4:8], 'big')
            max_leaves = (self.page_size - 8) // 4

            if n_leaves < max_leaves:
                leaf_offset = 8 + (n_leaves * 4)
                trunk_data[4:8] = (n_leaves + 1).to_bytes(4, 'big')
                trunk_data[leaf_offset:leaf_offset + 4] = page_number.to_bytes(4, 'big')
                self.write_page(self.freelist_trunk, bytes(trunk_data))
            else:
                new_trunk_data = bytearray(self.page_size)
                new_trunk_data[0:4] = self.freelist_trunk.to_bytes(4, 'big')
                new_trunk_data[4:8] = (1).to_bytes(4, 'big')
                new_trunk_data[8:12] = self.freelist_trunk.to_bytes(4, 'big')
                self.write_page(page_number, bytes(new_trunk_data))
                self.freelist_trunk = page_number

    # ---- close ----

    def close(self):
        """Close the pager, flushing any pending changes."""
        if self.in_transaction:
            self.rollback_transaction()
        if self.dirty_pages:
            self.flush()
            self.sync()
        self.cache.clear()
        self.dirty_pages.clear()
        self.vfs.close(self.handle)
