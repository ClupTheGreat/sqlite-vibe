# Complete SQLite Reimplementation in Python — Implementation Guide

> **Scope:** 100% pure Python, zero third-party dependencies (except `pytest` for testing).
> **Goal:** Full binary compatibility with SQLite 3.x `.db` files.
> **Architecture:** 10-layer stack, each with careful abstraction boundaries.

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Phase 0: Infrastructure & Utilities](#2-phase-0-infrastructure--utilities)
3. [Phase 1: Storage Layer (VFS + Pager)](#3-phase-1-storage-layer-vfs--pager)
4. [Phase 2: Record & B-Tree Engine](#4-phase-2-record--b-tree-engine)
5. [Phase 3: SQL Language (Lexer + Parser + AST)](#5-phase-3-sql-language-lexer--parser--ast)
6. [Phase 4: Bytecode Compiler & Virtual Machine](#6-phase-4-bytecode-compiler--virtual-machine)
7. [Phase 5: Schema & Catalog](#7-phase-5-schema--catalog)
8. [Phase 6: Transaction & Concurrency](#8-phase-6-transaction--concurrency)
9. [Phase 7: Full SQL Feature Set](#9-phase-7-full-sql-feature-set)
10. [Phase 8: CLI & Ecosystem](#10-phase-8-cli--ecosystem)
11. [Phase 9: Testing & Validation](#11-phase-9-testing--validation)
12. [Phase 10: Performance Tuning](#12-phase-10-performance-tuning)
13. [Implementation Milestones](#13-implementation-milestones)

---

## 1. Project Structure

```
sqlite-py/
├── pysqlite/
│   ├── __init__.py              # Public API, DB-API 2.0 interface
│   ├── vfs.py                   # Virtual File System abstraction
│   ├── pager.py                 # Page cache, journal, ACID
│   ├── cell.py                  # B-Tree cell serialization
│   ├── record.py                # SQLite record encoding/decoding
│   ├── btree.py                 # B-Tree engine (Cursors, split/merge)
│   ├── lexer.py                 # SQL tokenizer
│   ├── parser.py                # Recursive descent SQL parser
│   ├── ast.py                   # Typed AST node classes
│   ├── compile.py               # VDBE bytecode compiler
│   ├── opcode.py                # VDBE instruction set
│   ├── vm.py                    # Virtual machine (bytecode interpreter)
│   ├── schema.py                # Schema manager (sqlite_schema)
│   ├── transaction.py           # Transaction + savepoint manager
│   ├── functions/
│   │   ├── __init__.py          # Function registry
│   │   ├── aggregate.py         # COUNT, SUM, AVG, etc.
│   │   ├── scalar.py            # ABS, LENGTH, SUBSTR, etc.
│   │   ├── datetime.py          # DATE, TIME, DATETIME, etc.
│   │   ├── json.py              # JSON functions
│   │   ├── math.py              # ACOS, SIN, LOG, etc.
│   │   ├── window.py            # row_number, rank, lag, lead, etc.
│   │   └── fts.py               # Full-text search
│   ├── virtualtables/
│   │   ├── __init__.py          # Virtual table framework
│   │   ├── series.py            # generate_series
│   │   └── json_each.py         # json_each, json_tree
│   ├── trigram.py               # Trigram tokenizer for FTS
│   └── cli.py                   # Command-line REPL
├── tests/
│   ├── unit/
│   │   ├── test_vfs.py
│   │   ├── test_pager.py
│   │   ├── test_btree.py
│   │   ├── test_lexer.py
│   │   ├── test_parser.py
│   │   ├── test_compile.py
│   │   ├── test_vm.py
│   │   ├── test_schema.py
│   │   ├── test_transaction.py
│   │   ├── test_record.py
│   │   └── test_functions.py
│   ├── sql/
│   │   ├── test_ddl.py
│   │   ├── test_select.py
│   │   ├── test_insert.py
│   │   ├── test_update_delete.py
│   │   ├── test_joins.py
│   │   ├── test_expressions.py
│   │   ├── test_aggregates.py
│   │   ├── test_subqueries.py
│   │   ├── test_cte.py
│   │   ├── test_window.py
│   │   ├── test_triggers.py
│   │   ├── test_views.py
│   │   ├── test_indexes.py
│   │   ├── test_alter.py
│   │   ├── test_upsert.py
│   │   ├── test_fk.py
│   │   ├── test_generated_cols.py
│   │   ├── test_strict.py
│   │   ├── test_without_rowid.py
│   │   ├── test_json.py
│   │   ├── test_fts.py
│   │   └── test_pragmas.py
│   ├── compat/
│   │   ├── test_read_real_sqlite.py
│   │   └── test_write_real_sqlite.py
│   ├── stress/
│   │   ├── test_large_inserts.py
│   │   ├── test_concurrent.py
│   │   └── test_long_transactions.py
│   └── fuzz/
│       ├── test_random_sql.py
│       └── test_corrupt_db.py
├── examples/
│   └── demo.py
├── AGENTS.md                    # Reusable instructions for AI assistants
├── pyproject.toml               # Build config
└── README.md
```

### Build Configuration (`pyproject.toml`)

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "pysqlite"
version = "0.1.0"
description = "Complete SQLite reimplementation in pure Python"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-benchmark>=4.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

---

## 2. Phase 0: Infrastructure & Utilities

### 2.1 `util/bitwise.py` — Bit-level Operations

SQLite uses a specific variable-length integer encoding called "varint" (a variant of LEB128). Every integer stored in database pages, cell headers, and record serial types uses this encoding.

**Varint Encoding Algorithm:**

Each byte contributes 7 bits of data. The high bit (bit 7) is a continuation flag:
- If bit 7 = 1 → more bytes follow
- If bit 7 = 0 → this is the last byte

**Decoding (9-byte maximum):**

```
def decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    """
    Returns (value, bytes_consumed).
    
    Reads 1-9 bytes:
    - First 8 bytes: 7 data bits each, continuation bit = 1
    - 9th byte: all 8 bits are data, no continuation bit
    """
    result = 0
    for i in range(8):
        b = data[offset + i]
        result = (result << 7) | (b & 0x7F)
        if not (b & 0x80):
            return (result, i + 1)
    # 9th byte: full 8 bits
    b = data[offset + 8]
    result = (result << 8) | b
    return (result, 9)
```

**Encoding:**

```
def encode_varint(value: int) -> bytes:
    """Encode value as varint (1-9 bytes)."""
    if value <= 240:
        return bytes([value])
    if value <= 2287:
        return bytes([((value - 240) >> 8) + 241, (value - 240) & 0xFF])
    if value <= 67823:
        return bytes([249, ((value - 2288) >> 8) & 0xFF, (value - 2288) & 0xFF])
    # General case: up to 9 bytes
    bytes_out = []
    while value > 0:
        bytes_out.insert(0, value & 0x7F)
        value >>= 7
    bytes_out[-1] &= 0x7F
    for i in range(len(bytes_out) - 1):
        bytes_out[i] |= 0x80
    # Pad with leading continuation bytes if needed
    while len(bytes_out) < 9:
        bytes_out.insert(0, 0x80)
    return bytes(bytes_out)
```

**Two's Complement Handling:**

SQLite stores signed integers in big-endian twos complement. For sizes that don't align to 8-bit boundaries (e.g., 24-bit integer):

```
def decode_twos_complement(data: bytes) -> int:
    """Decode big-endian twos complement of arbitrary length."""
    value = int.from_bytes(data, 'big', signed=False)
    if data[0] & 0x80:  # negative
        bits = len(data) * 8
        value -= 1 << bits
    return value

def encode_twos_complement(value: int, byte_count: int) -> bytes:
    """Encode as big-endian twos complement with exact byte count."""
    if value < 0:
        value += 1 << (byte_count * 8)
    return value.to_bytes(byte_count, 'big')
```

### 2.2 `util/errors.py` — Error Hierarchy

```
class DatabaseError(Exception):
    """Base for all database errors."""
    code: int  # SQLite extended error code

class IOError(DatabaseError):           # SQLITE_IOERR (10)
class CorruptError(DatabaseError):      # SQLITE_CORRUPT (11)
class ConstraintViolation(DatabaseError): # SQLITE_CONSTRAINT (19)
class ReadOnlyError(DatabaseError):     # SQLITE_READONLY (8)
class NotADbError(DatabaseError):       # SQLITE_NOTADB (26)
class SchemaChangedError(DatabaseError):# SQLITE_SCHEMA (17)
class MisuseError(DatabaseError):       # SQLITE_MISUSE (21)
class FullError(DatabaseError):         # SQLITE_FULL (13)
class CantOpenError(DatabaseError):     # SQLITE_CANTOPEN (14)
class LockedError(DatabaseError):       # SQLITE_LOCKED (6)
class BusyError(DatabaseError):         # SQLITE_BUSY (5)
class NoMemError(DatabaseError):        # SQLITE_NOMEM (7)
class InterruptError(DatabaseError):    # SQLITE_INTERRUPT (9)
class AbortError(DatabaseError):        # SQLITE_ABORT (4)
class AuthError(DatabaseError):         # SQLITE_AUTH (23)
class RangeError(DatabaseError):        # SQLITE_RANGE (25)
class OverflowError(DatabaseError):     # SQLITE_OVERFLOW .. custom mapping
class MismatchError(DatabaseError):     # SQLITE_MISMATCH (20)
class FormatError(DatabaseError):       # SQLITE_FORMAT (24)
class InternalError(DatabaseError):     # SQLITE_INTERNAL (2)
class NoticeError(DatabaseError):       # SQLITE_NOTICE (27)
class WarningError(DatabaseError):      # SQLITE_WARNING (28)
class ProtocolError(DatabaseError):     # SQLITE_PROTOCOL (15)

# Extended constraint error codes:
class ConstraintPrimaryKeyError(ConstraintViolation):   # SQLITE_CONSTRAINT_PRIMARYKEY
class ConstraintUniqueError(ConstraintViolation):       # SQLITE_CONSTRAINT_UNIQUE
class ConstraintCheckError(ConstraintViolation):        # SQLITE_CONSTRAINT_CHECK
class ConstraintNotNullError(ConstraintViolation):      # SQLITE_CONSTRAINT_NOTNULL
class ConstraintForeignKeyError(ConstraintViolation):   # SQLITE_CONSTRAINT_FOREIGNKEY
class ConstraintTriggerError(ConstraintViolation):      # SQLITE_CONSTRAINT_TRIGGER
```

Each error stores:
- `code`: primary error code (8 bits)
- `extended_code`: extended error code (full 32 bits)
- `message`: human-readable description

### 2.3 `util/constants.py` — Shared Constants

**Database Header Constants:**
```
HEADER_MAGIC = b"SQLite format 3\000"          # 16 bytes, null-terminated
HEADER_SIZE = 100                               # First 100 bytes of page 1
HEADER_OFFSET_MAGIC = 0
HEADER_OFFSET_PAGE_SIZE = 16
HEADER_OFFSET_WRITE_FORMAT = 18
HEADER_OFFSET_READ_FORMAT = 19
HEADER_OFFSET_RESERVED_SPACE = 20
HEADER_OFFSET_MAX_EMBEDDED_FRACTION = 21
HEADER_OFFSET_MIN_EMBEDDED_FRACTION = 22
HEADER_OFFSET_LEAF_PAYLOAD_FRACTION = 23
HEADER_OFFSET_FILE_CHANGE_COUNTER = 24
HEADER_OFFSET_DATABASE_SIZE = 28
HEADER_OFFSET_FREELIST_TRUNK = 32
HEADER_OFFSET_FREELIST_COUNT = 36
HEADER_OFFSET_SCHEMA_COOKIE = 40
HEADER_OFFSET_SCHEMA_FORMAT = 44
HEADER_OFFSET_DEFAULT_CACHE_SIZE = 48
HEADER_OFFSET_LARGEST_ROOT_PAGE = 52
HEADER_OFFSET_TEXT_ENCODING = 56
HEADER_OFFSET_USER_VERSION = 60
HEADER_OFFSET_INCREMENTAL_VACUUM = 64
HEADER_OFFSET_APPLICATION_ID = 68
HEADER_OFFSET_RESERVED_BYTES = 72
HEADER_OFFSET_VERSION_VALID_FOR = 92
HEADER_OFFSET_SQLITE_VERSION_NUMBER = 96
```

**Journal Header Constants:**
```
JOURNAL_MAGIC = b"\xd9\xd5\x05\xf9\x20\xa1\x63\xd7"  # 8 bytes
JOURNAL_HEADER_SIZE = 28
JOURNAL_PAGE_SIZE_OFFSET = 8
JOURNAL_N_PAGES_OFFSET = 12
JOURNAL_CHECKSUM_OFFSET = 16
JOURNAL_SECTOR_SIZE = 512
```

**Page Type Flags (stored in first byte of page):**
```
PT_INTERIOR_INDEX = 0x02   # Interior index page
PT_INTERIOR_TABLE = 0x05   # Interior table page
PT_LEAF_INDEX = 0x0A       # Leaf index page
PT_LEAF_TABLE = 0x0D       # Leaf table page
```

**Lock States:**
```
LOCK_NONE = 0
LOCK_SHARED = 1
LOCK_RESERVED = 2
LOCK_PENDING = 3
LOCK_EXCLUSIVE = 4
```

**Text Encoding:**
```
ENCODING_UTF8 = 1
ENCODING_UTF16LE = 2
ENCODING_UTF16BE = 3
```

**Default Values:**
```
DEFAULT_PAGE_SIZE = 4096
MIN_PAGE_SIZE = 512
MAX_PAGE_SIZE = 65536
MAX_VARINT_BYTES = 9
MAX_EMBEDDED_PAYLOAD_FRACTION = 64
MIN_EMBEDDED_PAYLOAD_FRACTION = 32
LEAF_PAYLOAD_FRACTION = 32
MAX_COLUMNS = 2000  # SQLITE_MAX_COLUMN
MAX_PAGE_COUNT = 1073741823  # 2^31 - 1 pages of 65536 bytes = ~2^48 bytes
MAX_VARIABLE_NUMBER = 32766  # max binding parameters
MAX_TRIGGER_DEPTH = 1000
MAX_FUNCTION_ARG = 127
```

**Serial Type Constants (for record encoding):**
```
ST_NULL = 0
ST_INT8 = 1
ST_INT16 = 2
ST_INT24 = 3
ST_INT32 = 4
ST_INT48 = 5
ST_INT64 = 6
ST_FLOAT64 = 7
ST_ZERO = 8           # Integer 0, stored in 0 bytes
ST_ONE = 9            # Integer 1, stored in 0 bytes
ST_BLOB_BASE = 12     # serial_type >= 12 and even → BLOB of (n-12)/2 bytes
ST_TEXT_BASE = 13     # serial_type >= 13 and odd → TEXT of (n-13)/2 bytes
```

**Affinity Constants:**
```
AFFINITY_INTEGER = 0
AFFINITY_REAL = 1
AFFINITY_NUMERIC = 2
AFFINITY_TEXT = 3
AFFINITY_BLOB = 4
```

**Comparison Result Constants:**
```
CMP_LT = -1
CMP_EQ = 0
CMP_GT = 1
CMP_NE = 2  # SQL's "not equal" includes NULL handling
```

**Schema Table Layout:**
```
SQLITE_SCHEMA_TABLE = "sqlite_schema"  # or "sqlite_master" for backward compat
SCHEMA_COL_TYPE = 0   # 'table', 'index', 'view', 'trigger'
SCHEMA_COL_NAME = 1
SCHEMA_COL_TBL_NAME = 2
SCHEMA_COL_ROOTPAGE = 3
SCHEMA_COL_SQL = 4
SCHEMA_NUM_COLUMNS = 5
```

---

## 3. Phase 1: Storage Layer (VFS + Pager)

### 3.1 Virtual File System (`vfs.py`)

**Purpose:** Abstract all file I/O behind an interface so the database engine never touches raw file handles. This enables memory databases, testing with fake filesystems, and future extensions (encrypted VFS, network VFS).

**Interface:**

```python
class FileHandle:
    """Opaque wrapper around a file descriptor."""
    def __init__(self, fd: int, path: str):
        self.fd = fd
        self.path = path
        self.lock_state = LOCK_NONE
        self.is_memory = False
        self.mem_buffer: bytearray | None = None

class VFS:
    def open(self, path: str, flags: int) -> FileHandle:
        """
        Open or create a database file.
        flags: combination of SQLITE_OPEN_READONLY (0x01),
               SQLITE_OPEN_READWRITE (0x02), SQLITE_OPEN_CREATE (0x04)
        """
    
    def close(self, handle: FileHandle):
        """Close file and release all resources."""
    
    def read(self, handle: FileHandle, offset: int, amount: int) -> bytes:
        """Read exactly `amount` bytes starting at `offset`."""
    
    def write(self, handle: FileHandle, offset: int, data: bytes):
        """Write data at offset (must be sector-aligned for journal)."""
    
    def truncate(self, handle: FileHandle, size: int):
        """Truncate file to given size in bytes."""
    
    def sync(self, handle: FileHandle, flags: int):
        """Flush OS buffers to disk. flags: SQLITE_SYNC_NORMAL, SQLITE_SYNC_FULL, SQLITE_SYNC_DATAONLY."""
    
    def file_size(self, handle: FileHandle) -> int:
        """Return total file size in bytes."""
    
    def lock(self, handle: FileHandle, lock_type: int) -> bool:
        """
        Acquire a lock. Lock escalation is one-way:
        NONE → SHARED → RESERVED → PENDING → EXCLUSIVE
        Returns True if lock acquired, False if busy.
        """
    
    def unlock(self, handle: FileHandle, lock_type: int):
        """Release lock back to given lock_type (typically NONE or SHARED)."""
    
    def check_reserved_lock(self, handle: FileHandle) -> bool:
        """Check if another process holds a RESERVED or greater lock."""
    
    def sector_size(self, handle: FileHandle) -> int:
        """Return filesystem sector size (typically 512 or 4096)."""
    
    def delete(self, path: str):
        """Delete the file from disk."""
    
    def file_exists(self, path: str) -> bool:
        """Check if file exists."""
```

**OS VFS Implementation Details:**

**File opening:**
- Use `os.open()` with appropriate flags (`os.O_RDWR | os.O_BINARY | os.O_CREAT`)
- On Windows, also pass `os.O_NOINHERIT` and `_O_TEMPORARY` for temp files
- Use `_get_osfhandle()` to get Windows HANDLE for locking

**Read/Write:**
- Use `os.pread()` and `os.pwrite()` for thread-safe positional I/O (POSIX)
- On Windows, use `os.lseek()` + `os.read()` / `os.write()` with `threading.Lock` for safety
- All I/O must be done at sector-aligned offsets for journal writes

**Windows Locking Implementation:**

Windows locking uses `LockFileEx` / `UnlockFileEx` via `ctypes`:
```
SHARED lock:  LockFileEx(handle, 0, 0, 1, 0, overlap)  # shared, byte 0
RESERVED lock: LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, overlap)  # byte 1
PENDING lock: LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, overlap)  # byte 2
EXCLUSIVE lock: LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, overlap)  # byte 3
```

Windows has no `pread`/`pwrite`. Implement with:
```python
def _win_pread(fd, size, offset):
    import msvcrt
    handle = msvcrt.get_osfhandle(fd)
    # Use SetFilePointerEx + ReadFile via ctypes
    ...
```

**Memory VFS (for `:memory:` databases):**
```python
class MemoryVFS(VFS):
    def __init__(self):
        self.buffers: dict[str, bytearray] = {}
    
    def open(self, path, flags):
        if path not in self.buffers:
            self.buffers[path] = bytearray(HEADER_SIZE)  # empty db
        handle = FileHandle(-1, path)
        handle.is_memory = True
        handle.mem_buffer = self.buffers[path]
        return handle
    
    def read(self, handle, offset, amount):
        buf = handle.mem_buffer
        if offset + amount > len(buf):
            return b'\x00' * amount  # reading past end -> zeros
        return bytes(buf[offset:offset + amount])
    
    def write(self, handle, offset, data):
        buf = handle.mem_buffer
        end = offset + len(data)
        if end > len(buf):
            buf.extend(b'\x00' * (end - len(buf)))
        buf[offset:end] = data
    
    def file_size(self, handle):
        return len(handle.mem_buffer)
    
    def truncate(self, handle, size):
        buf = handle.mem_buffer
        if size < len(buf):
            del buf[size:]
        elif size > len(buf):
            buf.extend(b'\x00' * (size - len(buf)))
```

### 3.2 Pager (`pager.py`)

**Purpose:** The pager manages the database as an array of fixed-size pages. It provides page-level read/write, implements ACID via rollback journal, and manages the page cache.

**Data Structures:**

```python
class Pager:
    def __init__(self, vfs: VFS, path: str, flags: int):
        self.vfs = vfs
        self.handle = vfs.open(path, flags)
        self.page_size = DEFAULT_PAGE_SIZE
        self.total_pages = 0
        self.cache: dict[int, Page] = {}       # page_number -> Page
        self.dirty_pages: set[int] = set()      # pages modified but not yet flushed
        self.ref_count: dict[int, int] = {}     # pin count per page
        self.freelist_trunk: int = 0            # first freelist trunk page
        self.freelist_count: int = 0            # pages on freelist
        self.db_header: DatabaseHeader = None   # parsed header from page 1
        self.in_transaction: bool = False
        self.journal_fd = None
        self.journal_mode = JournalMode.DELETE  # DELETE | TRUNCATE | PERSIST | MEMORY | OFF | WAL
        self.schema_version = 0
        self.schema_cookie = 0
        self.file_change_counter = 0

class Page:
    def __init__(self, number: int, data: bytes, dirty: bool = False):
        self.number = number
        self.data = bytearray(data)
        self.dirty = dirty
```

**Page Lifecycle:**

```
                _________              _________
               |         |  read()    |         |
               |  Disk   | -------->  |  Cache  |
               |         | <--------  |         |
               |_________|  write()   |_________|
                               |
                               | modified
                               v
                          ___________
                         | Dirty Set |
                         |___________|
                               |
                         on flush/sync
                               |
                               v
                           ____|____
                          |  Disk   |
                          |_________|
```

**Initialize (opening a database):**

```python
def open_db(self):
    """Open an existing database or create a new one."""
    if self.vfs.file_size(self.handle) == 0:
        # New database: write header
        self._init_header()
        self.total_pages = 1
        self.vfs.sync(self.handle, SYNC_FULL)
    else:
        # Read header from page 1
        header_raw = self.vfs.read(self.handle, 0, HEADER_SIZE)
        self._parse_header(header_raw)
        self.total_pages = self.db_header.database_size
        # Hot journal recovery
        if self._hot_journal_exists():
            self._recover_hot_journal()
```

**Header Initialization:**

```python
def _init_header(self):
    """Write a default database header for a new database."""
    buf = bytearray(HEADER_SIZE)
    buf[0:16] = HEADER_MAGIC
    buf[16:18] = self.page_size.to_bytes(2, 'big')
    buf[18] = 1   # write format (1 = legacy, 2 = WAL)
    buf[19] = 1   # read format (1 = legacy, 2 = WAL)
    buf[20] = 0   # reserved space (no encryption)
    buf[21] = MAX_EMBEDDED_PAYLOAD_FRACTION
    buf[22] = MIN_EMBEDDED_PAYLOAD_FRACTION
    buf[23] = LEAF_PAYLOAD_FRACTION
    buf[24:28] = (1).to_bytes(4, 'big')  # file change counter starts at 1
    buf[28:32] = (1).to_bytes(4, 'big')  # database size = 1 page
    buf[40:44] = (1).to_bytes(4, 'big')  # schema cookie
    buf[44:48] = (4).to_bytes(4, 'big')  # schema format = 4 (support generated cols)
    buf[56:60] = ENCODING_UTF8.to_bytes(4, 'big')  # default encoding UTF-8
    buf[96:100] = (3040000).to_bytes(4, 'big')  # SQLite version 3.4.0
    self.vfs.write(self.handle, 0, bytes(buf))
```

**Header Parsing:**

```python
def _parse_header(self, data: bytes):
    """Parse the 100-byte database header."""
    if data[0:16] != HEADER_MAGIC:
        raise NotADbError("Not a SQLite database")
    self.page_size = int.from_bytes(data[16:18], 'big')
    if self.page_size == 1:
        self.page_size = 65536  # special case: 1 means 65536
    if self.page_size < MIN_PAGE_SIZE or self.page_size > MAX_PAGE_SIZE:
        raise CorruptError(f"Invalid page size: {self.page_size}")
    if (self.page_size & (self.page_size - 1)) != 0:
        raise CorruptError(f"Page size not power of 2: {self.page_size}")
    self.db_header = DatabaseHeader(
        page_size=self.page_size,
        write_format=data[18],
        read_format=data[19],
        reserved_space=data[20],
        file_change_counter=int.from_bytes(data[24:28], 'big'),
        database_size=int.from_bytes(data[28:32], 'big'),
        freelist_trunk=int.from_bytes(data[32:36], 'big'),
        freelist_count=int.from_bytes(data[36:40], 'big'),
        schema_cookie=int.from_bytes(data[40:44], 'big'),
        schema_format=int.from_bytes(data[44:48], 'big'),
        text_encoding=int.from_bytes(data[56:60], 'big'),
        user_version=int.from_bytes(data[60:64], 'big'),
        application_id=int.from_bytes(data[68:72], 'big'),
        version_valid_for=int.from_bytes(data[92:96], 'big'),
        sqlite_version=int.from_bytes(data[96:100], 'big'),
    )
```

**Page Reading:**

```python
def read_page(self, page_number: int) -> bytearray:
    """Read a page from cache or disk. Returns mutable bytearray."""
    if page_number < 1 or page_number > self.total_pages:
        raise CorruptError(f"Page {page_number} out of range")
    
    # Check cache first
    if page_number in self.cache:
        return self.cache[page_number].data
    
    # Read from disk
    offset = (page_number - 1) * self.page_size
    data = self.vfs.read(self.handle, offset, self.page_size)
    page = Page(page_number, data)
    self.cache[page_number] = page
    return page.data

def pin_page(self, page_number: int):
    """Pin a page in cache so it won't be evicted."""
    self.ref_count[page_number] = self.ref_count.get(page_number, 0) + 1

def unpin_page(self, page_number: int):
    """Release a pinned page."""
    self.ref_count[page_number] -= 1
    if self.ref_count[page_number] <= 0:
        del self.ref_count[page_number]
```

**Page Writing:**

```python
def write_page(self, page_number: int, data: bytes):
    """Mark a page as dirty (will be written to disk on flush)."""
    if page_number not in self.cache:
        page = Page(page_number, data)
        self.cache[page_number] = page
    else:
        self.cache[page_number].data = bytearray(data)
    self.cache[page_number].dirty = True
    self.dirty_pages.add(page_number)

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
```

**Rollback Journal Implementation:**

The rollback journal provides atomic commit. Before modifying any page, the original content is saved to the journal. On crash, the journal is automatically replayed to restore the database to its previous state.

**Journal File Format:**

```
|-----------------------|-----------------------|-----------------------|
|  Journal Header       |  Page 1 Original      |  Page 2 Original      |
|  (28 bytes)           |  (page_size bytes)    |  (page_size bytes)    |
|-----------------------|-----------------------|-----------------------|
|  Journal Header       |  Page N Original      |  Checksum             |
|  (28 bytes)           |  (page_size bytes)    |  (4 bytes)            |
|-----------------------|-----------------------|-----------------------|
```

Each "journal sector" starts with a journal header. Multiple sectors exist because the journal must be written in sector-sized chunks for safe crash recovery.

**Journal Header Layout (28 bytes):**

```
Offset  Size  Field
0       4     Journal magic (0xd9d505f9)
4       4     Size of database file in pages (when commit started)
8       4     Page size of database
12      4     Number of pages in this sector
16      4     Checksum of this header (simple XOR of all prior bytes)
20      4     First page number in this sector
24      4     Reserved
```

**Begin Transaction:**

```python
def begin_transaction(self, exclusive: bool = False):
    if self.in_transaction:
        raise MisuseError("Already in a transaction")
    
    if self.journal_mode == JournalMode.OFF:
        self.in_transaction = True
        return
    
    # Create journal file
    journal_path = self.handle.path + "-journal"
    journal_flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE
    self.journal_fd = self.vfs.open(journal_path, journal_flags)
    
    # Acquire RESERVED lock (or EXCLUSIVE if requested)
    lock = LOCK_EXCLUSIVE if exclusive else LOCK_RESERVED
    if not self.vfs.lock(self.handle, lock):
        self.vfs.close(self.journal_fd)
        self.journal_fd = None
        raise BusyError("Database is locked")
    
    # Write initial journal header (empty, just to claim the file)
    self._write_journal_header(0)
    self.vfs.sync(self.journal_fd, SYNC_NORMAL)
    
    self.in_transaction = True
    self._before_images: dict[int, bytes] = {}
```

**Journal Page Save (before first modification):**

```python
def _journal_page(self, page_number: int):
    """Save the original page content to journal before first modification."""
    if page_number in self._before_images:
        return  # already saved
    
    # Read page from disk (not from cache — cache may already be dirty)
    offset = (page_number - 1) * self.page_size
    original = self.vfs.read(self.handle, offset, self.page_size)
    self._before_images[page_number] = original
    
    # Write to journal
    self._write_journal_page(page_number, original)
```

**Commit Transaction:**

```python
def commit_transaction(self):
    """Commit all changes atomically."""
    if not self.in_transaction:
        return
    
    try:
        # Phase 1: flush dirty pages to disk
        self.flush()
        
        # Phase 2: sync database file
        self.vfs.sync(self.handle, SYNC_FULL)
        
        # Phase 3: sync journal (mark as committed)
        # Write "end of commit" marker: set nPages in first journal header to 0
        # This signals that the journal is no longer needed for recovery
        self._finalize_journal()
        
        # Phase 4: remove journal file
        if self.journal_mode == JournalMode.DELETE:
            self.vfs.close(self.journal_fd)
            self.vfs.delete(self.handle.path + "-journal")
        elif self.journal_mode == JournalMode.TRUNCATE:
            self.vfs.truncate(self.journal_fd, 0)
        elif self.journal_mode == JournalMode.PERSIST:
            # Zero out the journal header to mark it invalid
            self._zero_journal_header()
            self.vfs.sync(self.journal_fd, SYNC_FULL)
            self.vfs.close(self.journal_fd)
        elif self.journal_mode == JournalMode.MEMORY:
            # Journal was in memory; just discard
            pass
        
        # Increment change counter
        self.file_change_counter += 1
        self._write_header_field(24, self.file_change_counter.to_bytes(4, 'big'))
        
    except Exception:
        self._rollback_transaction()
        raise
    finally:
        self.in_transaction = False
        self._before_images = {}
        self.journal_fd = None
        # Release lock back to SHARED (or NONE if exclusive mode allows)
        self.vfs.unlock(self.handle, LOCK_SHARED)
```

**Rollback:**

```python
def rollback_transaction(self):
    """Restore database to state before the transaction began."""
    if not self.in_transaction:
        return
    
    try:
        # Restore before-images from journal
        for page_number, original in self._before_images.items():
            offset = (page_number - 1) * self.page_size
            self.vfs.write(self.handle, offset, original)
            # Remove from cache
            if page_number in self.cache:
                del self.cache[page_number]
        
        self.vfs.sync(self.handle, SYNC_FULL)
        
        # Remove journal
        if self.journal_fd is not None:
            self.vfs.close(self.journal_fd)
            self.vfs.delete(self.handle.path + "-journal")
    finally:
        self.in_transaction = False
        self._before_images = {}
        self.dirty_pages.clear()
        self.journal_fd = None
        self.vfs.unlock(self.handle, LOCK_SHARED)
```

**Hot Journal Recovery (on next open after crash):**

```python
def _hot_journal_exists(self) -> bool:
    """Check if a hot journal file needs recovery."""
    journal_path = self.handle.path + "-journal"
    if not self.vfs.file_exists(journal_path):
        return False
    
    try:
        jh = self.vfs.open(journal_path, SQLITE_OPEN_READONLY)
        header = self.vfs.read(jh, 0, 28)
        self.vfs.close(jh)
        
        # Check magic
        magic = int.from_bytes(header[0:4], 'big')
        if magic != 0xd9d505f9:
            return False
        
        # Check nPages: if 0, commit was successful, no recovery needed
        n_pages = int.from_bytes(header[12:16], 'big')
        return n_pages > 0
    except Exception:
        return False

def _recover_hot_journal(self):
    """Replay hot journal to restore database consistency."""
    journal_path = self.handle.path + "-journal"
    
    # Need EXCLUSIVE lock for recovery
    if not self.vfs.lock(self.handle, LOCK_EXCLUSIVE):
        raise BusyError("Cannot acquire lock for crash recovery")
    
    try:
        jh = self.vfs.open(journal_path, SQLITE_OPEN_READONLY)
        journal_size = self.vfs.file_size(jh)
        sector_size = self.vfs.sector_size(self.handle)
        
        offset = 0
        while offset < journal_size:
            # Read sector header
            header = self.vfs.read(jh, offset, 28)
            if len(header) < 28:
                break
            
            magic = int.from_bytes(header[0:4], 'big')
            if magic != 0xd9d505f9:
                break
            
            db_size = int.from_bytes(header[4:8], 'big')
            j_page_size = int.from_bytes(header[8:12], 'big')
            n_pages = int.from_bytes(header[12:16], 'big')
            first_page = int.from_bytes(header[20:24], 'big')
            
            if n_pages == 0:
                break  # commit completed
            
            # Restore each page in this sector
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
```

**Page Allocation & Freelist:**

```python
def allocate_page(self) -> int:
    """
    Allocate a new page from the freelist or extend the database.
    Returns the page number.
    """
    if self.freelist_count > 0:
        # Take from freelist
        page_num = self._pop_freelist()
        self.freelist_count -= 1
        self._update_freelist_headers()
    else:
        # Extend file
        self.total_pages += 1
        self.db_header.database_size = self.total_pages
    
    # Zero-fill the new page
    self.write_page(page_num, b'\x00' * self.page_size)
    return page_num

def free_page(self, page_number: int):
    """Add a page to the freelist for reuse."""
    self._push_freelist(page_number)
    self.freelist_count += 1
    self._update_freelist_headers()
    # Remove from cache
    if page_number in self.cache:
        del self.cache[page_number]
    self.dirty_pages.discard(page_number)

def _pop_freelist(self) -> int:
    """
    Remove and return a page from the freelist.
    Freelist structure: trunk pages form a linked list.
    Each trunk page:
      - Bytes 0-3: next trunk page (0 if none)
      - Bytes 4-7: number of leaf pointers on this trunk
      - Bytes 8+:  leaf page numbers (4 bytes each)
    """
    if self.freelist_trunk == 0:
        raise CorruptError("Freelist empty but count > 0")
    
    trunk_data = self.read_page(self.freelist_trunk)
    n_leaves = int.from_bytes(trunk_data[4:8], 'big')
    
    if n_leaves > 0:
        # Pop last leaf
        leaf_offset = 4 + (n_leaves * 4)  # last leaf pointer is 4-byte aligned
        leaf_page = int.from_bytes(trunk_data[leaf_offset:leaf_offset+4], 'big')
        # Decrement count
        trunk_data[4:8] = (n_leaves - 1).to_bytes(4, 'big')
        self.write_page(self.freelist_trunk, bytes(trunk_data))
        return leaf_page
    else:
        # This trunk page itself is free; return it and advance to next trunk
        next_trunk = int.from_bytes(trunk_data[0:4], 'big')
        page = self.freelist_trunk
        self.freelist_trunk = next_trunk
        return page

def _push_freelist(self, page_number: int):
    """Add a page to the freelist."""
    # Clear the page content
    self.write_page(page_number, b'\x00' * self.page_size)
    
    if self.freelist_trunk == 0:
        # Create a new trunk page
        self.freelist_trunk = page_number
        trunk_data = bytearray(self.page_size)
        trunk_data[0:4] = (0).to_bytes(4, 'big')  # no next trunk
        trunk_data[4:8] = (0).to_bytes(4, 'big')  # no leaves yet
        self.write_page(page_number, bytes(trunk_data))
    else:
        trunk_data = self.read_page(self.freelist_trunk)
        n_leaves = int.from_bytes(trunk_data[4:8], 'big')
        max_leaves = (self.page_size - 8) // 4
        
        if n_leaves < max_leaves:
            # Add to existing trunk
            leaf_offset = 8 + (n_leaves * 4)
            trunk_data[4:8] = (n_leaves + 1).to_bytes(4, 'big')
            trunk_data[leaf_offset:leaf_offset+4] = page_number.to_bytes(4, 'big')
            self.write_page(self.freelist_trunk, bytes(trunk_data))
        else:
            # This page becomes a new trunk; old trunk is its leaf
            new_trunk_data = bytearray(self.page_size)
            new_trunk_data[0:4] = self.freelist_trunk.to_bytes(4, 'big')  # points to old trunk
            new_trunk_data[4:8] = (1).to_bytes(4, 'big')  # one leaf (the old trunk)
            new_trunk_data[8:12] = self.freelist_trunk.to_bytes(4, 'big')
            self.write_page(page_number, bytes(new_trunk_data))
            self.freelist_trunk = page_number
```

**Cache Eviction (LRU):**

```python
def _evict_page(self):
    """Evict the least-recently-used unpinned page from cache."""
    # Find unpinned pages
    candidates = [p for p in self.cache if self.ref_count.get(p, 0) == 0]
    if not candidates:
        return  # all pages pinned; cannot evict
    # Evict the oldest (by key order — but we track access order)
    oldest = min(candidates, key=lambda p: self._access_time.get(p, 0))
    del self.cache[oldest]
    if oldest in self._access_time:
        del self._access_time[oldest]

def _accessed(self, page_number: int):
    """Record that a page was accessed (for LRU)."""
    self._access_time[page_number] = self._clock
    self._clock += 1
```

**WAL Mode (Write-Ahead Log) — Overview:**

The WAL mode provides better concurrency (readers don't block writers). It replaces the rollback journal with a separate "WAL" file that accumulates changes. Readers read from the original database plus the WAL. When the WAL gets too large, a "checkpoint" merges WAL content back into the database.

WAL format will be detailed in a later section since it's complex. Start with rollback journal.

---

## 4. Phase 2: Record & B-Tree Engine

### 4.1 Cell Format (`cell.py`)

Cells are the fundamental unit of data within B-Tree pages. There are four cell types corresponding to the four page types.

**Table Leaf Cell:**

```
[varint: payload_length]
[varint: rowid]
[bytes: payload]   // the actual record data
```

The payload_length is the byte count of the payload. The rowid is the integer key (64-bit). The payload is the serialized record.

**Table Interior Cell:**

```
[varint: left_child_page]  // page number of left subtree
[varint: key]              // separator key (rowid)
```

**Index Leaf Cell:**

```
[varint: payload_length]
[bytes: payload]  // the indexed columns as a record (no rowid unless included)
```

**Index Interior Cell:**

```
[varint: left_child_page]
[varint: payload_length]
[bytes: payload]
```

**Cell Overflow:**

When a cell's payload exceeds about 25% of page size, it's stored as overflow:
- The first part is stored inline in the cell
- The rest is stored on overflow pages chained together

Maximum local payload = ((page_size - cell_offset) * max_embedded / 100) - 4
Where max_embedded = page[21] (default 64, meaning 64% of usable space)

Overflow page format:
```
[4 bytes: next_overflow_page (0 if last)]
[usable_size - 4 bytes: overflow data]
```

**Cell Implementation:**

```python
class Cell:
    """Base class for all cell types."""
    __slots__ = ()
    
    def serialize(self) -> bytes:
        raise NotImplementedError
    
    @classmethod
    def parse(cls, data: bytes, page_type: int) -> 'Cell':
        raise NotImplementedError

class TableLeafCell(Cell):
    __slots__ = ('payload_length', 'rowid', 'payload')
    
    def __init__(self, rowid: int, payload: bytes):
        self.rowid = rowid
        self.payload = payload
        self.payload_length = len(payload)
    
    def serialize(self) -> bytes:
        return encode_varint(self.payload_length) + encode_varint(self.rowid) + self.payload
    
    @classmethod
    def parse(cls, data: bytes) -> 'TableLeafCell':
        offset = 0
        payload_length, consumed = decode_varint(data, offset)
        offset += consumed
        rowid, consumed = decode_varint(data, offset)
        offset += consumed
        payload = data[offset:offset + payload_length]
        return cls(rowid, payload)

class TableInteriorCell(Cell):
    __slots__ = ('left_child_page', 'key')
    
    def __init__(self, left_child_page: int, key: int):
        self.left_child_page = left_child_page
        self.key = key
    
    def serialize(self) -> bytes:
        return encode_varint(self.left_child_page) + encode_varint(self.key)
    
    @classmethod
    def parse(cls, data: bytes) -> 'TableInteriorCell':
        offset = 0
        left_child, consumed = decode_varint(data, offset)
        offset += consumed
        key, consumed = decode_varint(data, offset)
        return cls(left_child, key)

class IndexLeafCell(Cell):
    __slots__ = ('payload_length', 'payload')
    
    def __init__(self, payload: bytes):
        self.payload = payload
        self.payload_length = len(payload)
    
    def serialize(self) -> bytes:
        return encode_varint(self.payload_length) + self.payload
    
    @classmethod
    def parse(cls, data: bytes) -> 'IndexLeafCell':
        offset = 0
        payload_length, consumed = decode_varint(data, offset)
        offset += consumed
        payload = data[offset:offset + payload_length]
        return cls(payload)

class IndexInteriorCell(Cell):
    __slots__ = ('left_child_page', 'payload_length', 'payload')
    
    def __init__(self, left_child_page: int, payload: bytes):
        self.left_child_page = left_child_page
        self.payload = payload
        self.payload_length = len(payload)
    
    def serialize(self) -> bytes:
        return (encode_varint(self.left_child_page) +
                encode_varint(self.payload_length) +
                self.payload)
    
    @classmethod
    def parse(cls, data: bytes) -> 'IndexInteriorCell':
        offset = 0
        left_child, consumed = decode_varint(data, offset)
        offset += consumed
        payload_length, consumed = decode_varint(data, offset)
        offset += consumed
        payload = data[offset:offset + payload_length]
        return cls(left_child, payload)
```

### 4.2 Record Encoding (`record.py`)

**Serial Type System:**

SQLite uses a compact self-describing format where each column's type and size are encoded in a single varint called the "serial type."

**Serial Type Encoding:**

```
Type Codes:
0  → NULL value (0 bytes)
1  → signed 8-bit integer (1 byte, big-endian twos complement)
2  → signed 16-bit integer (2 bytes)
3  → signed 24-bit integer (3 bytes)
4  → signed 32-bit integer (4 bytes)
5  → signed 48-bit integer (6 bytes)
6  → signed 64-bit integer (8 bytes)
7  → IEEE 754 64-bit float (8 bytes, big-endian)
8  → integer 0 (0 bytes, implicit value 0)
9  → integer 1 (0 bytes, implicit value 1)
10 → reserved
11 → reserved
12+ even → BLOB of (type-12)/2 bytes
13+ odd  → TEXT of (type-13)/2 bytes
```

**Record Format:**

```
[varint: header_size]           // total byte count of serial types array
[varint: serial_type_1]
[varint: serial_type_2]
  ...
[varint: serial_type_N]
[bytes: value_1]
[bytes: value_2]
  ...
[bytes: value_N]
```

**Implementation:**

```python
import struct

class Record:
    __slots__ = ('columns',)
    
    def __init__(self, columns: list[tuple[int, Any]]):
        """
        columns: list of (serial_type, value) pairs.
        serial_type can be computed automatically from value.
        """
        self.columns = columns
    
    @staticmethod
    def serial_type(value) -> int:
        """Determine the serial type code for a Python value."""
        if value is None:
            return 0
        if isinstance(value, bool):
            return 1 if value else 0  # bool is int subclass; 8-bit
        if isinstance(value, int):
            if value == 0:
                return 8
            if value == 1:
                return 9
            if -128 <= value <= 127:
                return 1
            if -32768 <= value <= 32767:
                return 2
            if -8388608 <= value <= 8388607:
                return 3
            if -2147483648 <= value <= 2147483647:
                return 4
            if -140737488355328 <= value <= 140737488355327:
                return 5
            return 6
        if isinstance(value, float):
            return 7
        if isinstance(value, (bytes, bytearray)):
            length = len(value)
            return 12 + 2 * length
        if isinstance(value, str):
            encoded = value.encode('utf-8')
            length = len(encoded)
            return 13 + 2 * length
        raise ValueError(f"Cannot serialize type: {type(value)}")
    
    @staticmethod
    def serial_type_to_bytes(st: int, value) -> bytes:
        """Convert a Python value to raw bytes given its serial type."""
        if st == 0:  # NULL
            return b''
        if st == 1:  # INT8
            return struct.pack('>b', value)
        if st == 2:  # INT16
            return struct.pack('>h', value)
        if st == 3:  # INT24
            if value < 0:
                value += 1 << 24
            return value.to_bytes(3, 'big')
        if st == 4:  # INT32
            return struct.pack('>i', value)
        if st == 5:  # INT48
            if value < 0:
                value += 1 << 48
            return value.to_bytes(6, 'big')
        if st == 6:  # INT64
            return struct.pack('>q', value)
        if st == 7:  # FLOAT64
            return struct.pack('>d', value)
        if st == 8:  # ZERO
            return b''
        if st == 9:  # ONE
            return b''
        if st >= 12 and st % 2 == 0:  # BLOB
            length = (st - 12) // 2
            if isinstance(value, str):
                value = value.encode('utf-8')
            return bytes(value[:length])
        if st >= 13 and st % 2 == 1:  # TEXT
            length = (st - 13) // 2
            if isinstance(value, str):
                encoded = value.encode('utf-8')
            else:
                encoded = str(value).encode('utf-8')
            return encoded[:length]
        raise ValueError(f"Unknown serial type: {st}")
    
    @staticmethod
    def bytes_to_value(st: int, data: bytes) -> Any:
        """Convert raw bytes back to a Python value given serial type."""
        if st == 0:
            return None
        if st == 1:
            return struct.unpack('>b', data)[0]
        if st == 2:
            return struct.unpack('>h', data)[0]
        if st == 3:
            val = int.from_bytes(data, 'big')
            if val >= 1 << 23:
                val -= 1 << 24
            return val
        if st == 4:
            return struct.unpack('>i', data)[0]
        if st == 5:
            val = int.from_bytes(data, 'big')
            if val >= 1 << 47:
                val -= 1 << 48
            return val
        if st == 6:
            return struct.unpack('>q', data)[0]
        if st == 7:
            return struct.unpack('>d', data)[0]
        if st == 8:
            return 0
        if st == 9:
            return 1
        if st >= 12 and st % 2 == 0:
            return data  # BLOB
        if st >= 13 and st % 2 == 1:
            return data.decode('utf-8')  # TEXT
        raise ValueError(f"Unknown serial type: {st}")
    
    def encode(self) -> bytes:
        """Serialize the record to bytes."""
        serial_types = []
        values_bytes = b''
        for st, value in self.columns:
            serial_types.append(st)
            values_bytes += self.serial_type_to_bytes(st, value)
        
        # Compute header
        header_data = b''
        for st in serial_types:
            header_data += encode_varint(st)
        
        header_length = len(header_data)
        result = encode_varint(header_length + 1)  # +1 for the header_size varint itself
        result += header_data
        result += values_bytes
        return result
    
    @classmethod
    def decode(cls, data: bytes, offset: int = 0) -> tuple['Record', int]:
        """
        Decode a record from bytes.
        Returns (Record, bytes_consumed).
        """
        header_size, consumed = decode_varint(data, offset)
        offset += consumed
        header_end = offset + header_size - 1  # -1 because header_size includes the size varint
        
        serial_types = []
        while offset < header_end:
            st, consumed = decode_varint(data, offset)
            serial_types.append(st)
            offset += consumed
        
        values = []
        for st in serial_types:
            if st == 0:
                values.append((st, None))
            elif st == 8:
                values.append((st, 0))
            elif st == 9:
                values.append((st, 1))
            elif st < 8:  # 1-7: fixed-size
                size = [0, 1, 2, 3, 4, 6, 8][st]
                val_data = data[offset:offset + size]
                values.append((st, cls.bytes_to_value(st, val_data)))
                offset += size
            elif st >= 12:
                if st % 2 == 0:  # BLOB
                    size = (st - 12) // 2
                else:  # TEXT
                    size = (st - 13) // 2
                val_data = data[offset:offset + size]
                values.append((st, cls.bytes_to_value(st, val_data)))
                offset += size
        
        return cls(values), offset
    
    def get_values(self) -> list[Any]:
        """Return just the Python values without serial type info."""
        return [v for _, v in self.columns]
```

### 4.3 B-Tree (`btree.py`)

**Page Layout:**

Each database page (header page aside) is one of four B-Tree page types. The layout within a page:

```
|-----------------------|
| Page Header (8-12b)   |
|-----------------------|
| Cell Pointer Array    |
| (2 bytes per cell)    |
| ...                   |
|-----------------------|
| Free Space            |
| ...                   |
|-----------------------|
| Unallocated Space     |
| ...                   |
|-----------------------|
| Cell Content           |
| (grows downward)      |
|-----------------------|
```

**Page Header Format:**

**Leaf Table Page (0x0D):**
```
Offset  Size  Field
0       1     Page type (0x0D)
1       2     First freeblock offset (0 if none)
3       2     Number of cells
5       2     Start of cell content area
7       1     Fragmented free bytes count
8       4     Rightmost child page (for interior pages only)
```

**Interior Table Page (0x05):**
Same header + 4 bytes: rightmost child page number (offset 8-11).

**Leaf Index Page (0x0A):**
Same as leaf table, but no rightmost child.

**Interior Index Page (0x02):**
Same as interior table (has rightmost child).

**Cell Pointer Array:**

An array of 2-byte integers (big-endian), each pointing to the byte offset of a cell within the page. Pointers are stored in key order (ascending by rowid for tables, by key for indexes).

**Freeblock Chain:**

When cells are deleted, their space is tracked via a linked list of freeblocks within the page:
```
[2 bytes: next freeblock offset (0 if end)]
[2 bytes: size of this freeblock]
```

**Implementation:**

```python
class BTreePage:
    __slots__ = (
        'pager', 'page_number', 'page_type', 'first_freeblock',
        'cell_count', 'cell_content_offset', 'fragmented_free_bytes',
        'right_child', 'cell_pointers', 'raw_data', 'dirty'
    )
    
    def __init__(self, pager: 'Pager', page_number: int):
        self.pager = pager
        self.page_number = page_number
        self.raw_data = bytearray(pager.read_page(page_number))
        self.dirty = False
        self._parse_header()
        self._parse_cell_pointers()
    
    def _parse_header(self):
        data = self.raw_data
        self.page_type = data[0]
        self.first_freeblock = int.from_bytes(data[1:3], 'big')
        self.cell_count = int.from_bytes(data[3:5], 'big')
        self.cell_content_offset = int.from_bytes(data[5:7], 'big')
        self.fragmented_free_bytes = data[7]
        
        if self.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX):
            self.right_child = int.from_bytes(data[8:12], 'big')
        else:
            self.right_child = 0
    
    def _write_header(self):
        data = self.raw_data
        data[0] = self.page_type
        data[1:3] = self.first_freeblock.to_bytes(2, 'big')
        data[3:5] = self.cell_count.to_bytes(2, 'big')
        data[5:7] = self.cell_content_offset.to_bytes(2, 'big')
        data[7] = self.fragmented_free_bytes
        
        if self.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX):
            data[8:12] = self.right_child.to_bytes(4, 'big')
    
    def _parse_cell_pointers(self):
        """Read the cell pointer array at the start of the page."""
        self.cell_pointers = []
        for i in range(self.cell_count):
            offset = 8 if self.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX) else 8
            idx = offset + (i * 2)
            ptr = int.from_bytes(self.raw_data[idx:idx+2], 'big')
            self.cell_pointers.append(ptr)
    
    def read_cell(self, index: int) -> bytes:
        """Read the raw bytes of cell at given index."""
        if index < 0 or index >= self.cell_count:
            raise IndexError(f"Cell index {index} out of range")
        ptr = self.cell_pointers[index]
        end_ptr = self._find_cell_end(index)
        return bytes(self.raw_data[ptr:end_ptr])
    
    def _find_cell_end(self, index: int) -> int:
        """Find where this cell's data ends (next cell start or free space)."""
        if index + 1 < self.cell_count:
            next_ptr = self.cell_pointers[index + 1]
            # Cells stored in descending offset order
            if next_ptr < self.cell_pointers[index]:
                return next_ptr
            # Descending: earlier index = higher offset
            for i in range(self.cell_count - 1, -1, -1):
                if self.cell_pointers[i] < self.cell_pointers[index]:
                    return self.cell_pointers[i]
        return self.cell_content_offset  # last cell goes to content area start
    
    def insert_cell(self, index: int, cell_data: bytes):
        """Insert a cell at the given index position."""
        # Defragment if needed
        if self._needs_defrag():
            self._defragment()
        
        # Find space for the cell
        cell_offset = self._allocate_space(len(cell_data))
        
        # Write cell data
        self.raw_data[cell_offset:cell_offset + len(cell_data)] = cell_data
        
        # Insert pointer
        ptr_offset = self._pointer_offset(index)
        # Shift existing pointers
        next_ptr_offset = self._pointer_offset(self.cell_count)
        for i in range(self.cell_count, index, -1):
            src = self._pointer_offset(i - 1)
            dst = self._pointer_offset(i)
            self.raw_data[dst:dst+2] = self.raw_data[src:src+2]
        
        # Write new pointer
        self.raw_data[ptr_offset:ptr_offset+2] = cell_offset.to_bytes(2, 'big')
        self.cell_count += 1
        self._write_header()
        self.dirty = True
    
    def delete_cell(self, index: int):
        """Remove a cell at given index. Its space becomes a freeblock."""
        # Read the cell data
        cell_data = self.read_cell(index)
        cell_offset = self.cell_pointers[index]
        cell_size = len(cell_data)
        
        # Add to freeblock chain
        self._add_freeblock(cell_offset, cell_size)
        
        # Remove pointer
        for i in range(index, self.cell_count - 1):
            dst = self._pointer_offset(i)
            src = self._pointer_offset(i + 1)
            self.raw_data[dst:dst+2] = self.raw_data[src:src+2]
        
        self.cell_count -= 1
        self.cell_pointers.pop(index)
        self._write_header()
        self.dirty = True
    
    def _pointer_offset(self, index: int) -> int:
        """Get the byte offset in the page for cell pointer at index."""
        header_size = 8 if self.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX) else 8
        return header_size + (index * 2)
    
    def _allocate_space(self, size: int) -> int:
        """Allocate space of given size. Returns offset where data starts."""
        # Try freeblock first
        offset = self._freeblock_alloc(size)
        if offset != 0:
            return offset
        
        # Allocate from the end of the cell content area
        old_offset = self.cell_content_offset
        new_offset = old_offset - size
        if new_offset < self._pointer_offset(self.cell_count):
            self._defragment()
            return self._allocate_space(size)
        self.cell_content_offset = new_offset
        self._write_header()
        self.dirty = True
        return new_offset
    
    def _freeblock_alloc(self, size: int) -> int:
        """
        Try to allocate from a freeblock.
        Returns the offset (0 if no suitable freeblock).
        """
        prev = 0
        current = self.first_freeblock
        while current != 0:
            block_size = int.from_bytes(self.raw_data[current+2:current+4], 'big')
            if block_size >= size:
                # Found a block large enough
                if block_size - size >= 4:
                    # Split the block
                    remaining = block_size - size
                    new_off = current + size
                    self.raw_data[new_off:new_off+2] = self.raw_data[current:current+2]  # next ptr
                    self.raw_data[new_off+2:new_off+4] = remaining.to_bytes(2, 'big')
                    if prev == 0:
                        self.first_freeblock = new_off
                    else:
                        self.raw_data[prev:prev+2] = new_off.to_bytes(2, 'big')
                else:
                    # Use whole block
                    if prev == 0:
                        self.first_freeblock = int.from_bytes(self.raw_data[current:current+2], 'big')
                    else:
                        self.raw_data[prev:prev+2] = self.raw_data[current:current+2]
                    size = block_size  # use entire block
                
                self._write_header()
                self.dirty = True
                return current
            
            prev = current
            next_off = int.from_bytes(self.raw_data[current:current+2], 'big')
            current = next_off
        
        return 0  # no suitable freeblock
    
    def _add_freeblock(self, offset: int, size: int):
        """Add a freeblock to the chain."""
        self.raw_data[offset:offset+2] = self.first_freeblock.to_bytes(2, 'big')
        self.raw_data[offset+2:offset+4] = size.to_bytes(2, 'big')
        self.first_freeblock = offset
        if size < 4:
            self.fragmented_free_bytes += size
        self._write_header()
        self.dirty = True
    
    def _needs_defrag(self) -> bool:
        """Check if defragmentation is beneficial."""
        # If fragmented free bytes > threshold, defrag
        return self.fragmented_free_bytes > (self.cell_content_offset * 0.1)
    
    def _defragment(self):
        """Compact all cells to contiguous space and reset freeblock chain."""
        # Collect all cells in order
        cells = []
        for i in range(self.cell_count - 1, -1, -1):
            cells.append(self.read_cell(i))
        
        # Calculate new layout: pointers at top, content at bottom
        usable_space = self.cell_content_offset  # old content area start
        new_content_end = usable_space
        
        # Write cells from bottom up
        for i, cell_data in enumerate(cells):
            size = len(cell_data)
            new_offset = new_content_end - size
            self.raw_data[new_offset:new_offset + size] = cell_data
            # Update pointer (cells in reverse order, so last inserted (index 0) goes to bottom)
            self.cell_pointers[self.cell_count - 1 - i] = new_offset
            new_content_end = new_offset
        
        # Update cell pointers in page
        for i in range(self.cell_count):
            ptr_offset = self._pointer_offset(i)
            self.raw_data[ptr_offset:ptr_offset+2] = self.cell_pointers[i].to_bytes(2, 'big')
        
        # Reset freeblock chain
        self.first_freeblock = 0
        self.fragmented_free_bytes = 0
        self.cell_content_offset = new_content_end
        
        self._write_header()
        self.dirty = True
    
    def flush(self):
        """Write the page back to disk if dirty."""
        if self.dirty:
            self._write_header()
            self.pager.write_page(self.page_number, bytes(self.raw_data))
            self.dirty = False
    
    def is_leaf(self) -> bool:
        return self.page_type in (PT_LEAF_TABLE, PT_LEAF_INDEX)
    
    def is_table(self) -> bool:
        return self.page_type in (PT_LEAF_TABLE, PT_INTERIOR_TABLE)
```

**B-Tree Cursor:**

```python
class BTreeCursor:
    """
    A cursor for navigating a B-Tree.
    
    Position tracking:
    - Each level of the tree is tracked with a (page_number, cell_index) pair
    - stack: list of (page_number, cell_index) from root to current depth
    """
    
    def __init__(self, btree: 'BTree', root_page: int):
        self.btree = btree
        self.root_page = root_page
        self.stack: list[tuple[int, int]] = []  # (page_number, cell_index) per level
        self.eof = False
        self.bof = True  # before first record
    
    def first(self):
        """Position cursor at the first (leftmost) entry."""
        page_num = self.root_page
        page = BTreePage(self.btree.pager, page_num)
        
        while page.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX):
            # Follow leftmost child
            first_cell = page.read_cell(0)
            if page.page_type == PT_INTERIOR_TABLE:
                cell = TableInteriorCell.parse(first_cell)
                self.stack.append((page_num, 0))
                page_num = cell.left_child_page
            else:
                cell = IndexInteriorCell.parse(first_cell)
                self.stack.append((page_num, 0))
                page_num = cell.left_child_page
            page = BTreePage(self.btree.pager, page_num)
        
        # Now on a leaf page: position at cell 0
        if page.cell_count == 0:
            self.eof = True
            return
        self.stack.append((page.page_number, 0))
        self.eof = False
        self.bof = False
    
    def last(self):
        """Position cursor at the last (rightmost) entry."""
        page_num = self.root_page
        page = BTreePage(self.btree.pager, page_num)
        
        while page.page_type in (PT_INTERIOR_TABLE, PT_INTERIOR_INDEX):
            last_idx = page.cell_count - 1
            if last_idx >= 0:
                last_cell = page.read_cell(last_idx)
                if page.page_type == PT_INTERIOR_TABLE:
                    cell = TableInteriorCell.parse(last_cell)
                    self.stack.append((page_num, last_idx + 1))  # +1 for right_child
                    page_num = cell.left_child_page  # ??? 
                else:
                    # Interior cell: follow rightmost child
                    pass  # need to handle right_child
            else:
                # No cells: follow right_child directly
                self.stack.append((page_num, 0))
                page_num = page.right_child
            page = BTreePage(self.btree.pager, page_num)
        
        # On leaf: last cell
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
        
        # Pop leaf position
        page_num, cell_idx = self.stack.pop()
        
        # Try next cell on this page
        page = BTreePage(self.btree.pager, page_num)
        if cell_idx + 1 < page.cell_count:
            self.stack.append((page_num, cell_idx + 1))
            return
        
        # Walk up the stack until we find an interior page with more cells
        while self.stack:
            parent_num, parent_idx = self.stack.pop()
            parent = BTreePage(self.btree.pager, parent_num)
            
            if parent_idx < parent.cell_count:
                # Move to next cell in parent, then descend to its leftmost child
                self.stack.append((parent_num, parent_idx))
                
                # Read the cell to get left_child
                cell_data = parent.read_cell(parent_idx)
                if parent.page_type == PT_INTERIOR_TABLE:
                    cell = TableInteriorCell.parse(cell_data)
                    next_page = cell.left_child_page
                else:
                    cell = IndexInteriorCell.parse(cell_data)
                    next_page = cell.left_child_page
                
                # Descend to leftmost leaf of that subtree
                while True:
                    next_pg = BTreePage(self.btree.pager, next_page)
                    if next_pg.is_leaf():
                        self.stack.append((next_page, 0))
                        return
                    else:
                        cell_data = next_pg.read_cell(0)
                        if next_pg.page_type == PT_INTERIOR_TABLE:
                            cell = TableInteriorCell.parse(cell_data)
                            self.stack.append((next_page, 0))
                            next_page = cell.left_child_page
                        else:
                            cell = IndexInteriorCell.parse(cell_data)
                            self.stack.append((next_page, 0))
                            next_page = cell.left_child_page
            else:
                # This was the last cell on parent; continue going up
                continue
        
        self.eof = True
    
    def prev(self):
        """Move cursor to previous entry in key order."""
        if self.bof:
            return
        
        page_num, cell_idx = self.stack.pop()
        page = BTreePage(self.btree.pager, page_num)
        
        if cell_idx > 0:
            self.stack.append((page_num, cell_idx - 1))
            # Descend to rightmost leaf of the left subtree
            # ...
        else:
            # Walk up
            while self.stack:
                parent_num, parent_idx = self.stack.pop()
                if parent_idx > 0:
                    self.stack.append((parent_num, parent_idx - 1))
                    # Descend to rightmost leaf
                    return
            self.bof = True
    
    def seek(self, key: int) -> bool:
        """
        Position cursor on the first entry >= key.
        Returns True if exact match found.
        """
        self.stack = []
        page_num = self.root_page
        exact_match = False
        
        while True:
            page = BTreePage(self.btree.pager, page_num)
            
            if page.is_leaf():
                # Binary search on leaf
                lo, hi = 0, page.cell_count - 1
                found_idx = -1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    cell_data = page.read_cell(mid)
                    if page.page_type == PT_LEAF_TABLE:
                        cell = TableLeafCell.parse(cell_data)
                        cell_key = cell.rowid
                    else:
                        # Index leaf: extract key from record
                        rec, _ = Record.decode(cell_data)
                        cell_key = rec.get_values()[0]  # first column is key
                    
                    if cell_key < key:
                        lo = mid + 1
                    elif cell_key > key:
                        hi = mid - 1
                    else:
                        found_idx = mid
                        exact_match = True
                        break
                
                if found_idx == -1:
                    found_idx = lo  # position at insertion point
                
                if found_idx >= page.cell_count:
                    self.eof = True
                else:
                    self.stack.append((page_num, found_idx))
                    self.eof = False
                return exact_match
            
            else:  # Interior page
                # Binary search on interior page to find child
                lo, hi = 0, page.cell_count - 1
                child = page.right_child  # default: go right
                mid = -1
                
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
                        child = cell.left_child_page  # Actually, need right child of this cell
                    elif cell_key > key:
                        hi = mid - 1
                        child = cell.left_child_page if mid == 0 else ...
                    else:
                        # Exact match on interior page: descend to this cell's subtree
                        child = cell.left_child_page
                        self.stack.append((page_num, mid))
                        page_num = child
                        exact_match = True
                        break
                
                if mid == -1 or lo > hi:
                    # Descend to appropriate child
                    self.stack.append((page_num, lo if lo < page.cell_count else page.right_child))
                    page_num = child
        
        return exact_match
    
    def current_key(self) -> int:
        """Return the key (rowid for table, first column for index) at current position."""
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
        """Return the payload at current position (table leaf only)."""
        page_num, cell_idx = self.stack[-1]
        page = BTreePage(self.btree.pager, page_num)
        cell_data = page.read_cell(cell_idx)
        
        if page.page_type == PT_LEAF_TABLE:
            cell = TableLeafCell.parse(cell_data)
            return cell.payload
        raise TypeError("Not a leaf table cursor")
    
    def insert(self, key: int, rowid: int, payload: bytes):
        """Insert a new entry."""
        # Navigate to the leaf page where the key should be inserted
        page_num = self.root_page
        page = BTreePage(self.btree.pager, page_num)
        
        # Find path to leaf
        path = []
        while not page.is_leaf():
            # Binary search to find which child to follow
            cell_data = None
            for i in range(page.cell_count):
                data = page.read_cell(i)
                if page.page_type == PT_INTERIOR_TABLE:
                    cell = TableInteriorCell.parse(data)
                    if key < cell.key:
                        path.append((page_num, i))
                        page_num = cell.left_child_page
                        break
                    elif i == page.cell_count - 1:
                        path.append((page_num, page.right_child))
                        page_num = page.right_child
                        break
                else:
                    # Index interior
                    pass
            page = BTreePage(self.btree.pager, page_num)
        
        # Now on leaf page
        cell_data = None
        if page.page_type == PT_LEAF_TABLE:
            cell_data = TableLeafCell(rowid, payload).serialize()
        else:
            cell_data = IndexLeafCell(payload).serialize()
        
        # Find insertion position
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
        
        page.insert_cell(insert_idx, cell_data)
        
        # Check if page needs splitting
        if page.cell_content_offset <= self._pointer_offset(page.cell_count) + 4:
            self._balance(path, page, insert_idx)
    
    def _balance(self, path: list, page: BTreePage, insert_idx: int):
        """
        Balance the tree after an insertion.
        Splits the page if full, possibly cascading splits upward.
        """
        # Implementation: split page into two, promote middle key to parent
        # If no parent, create new root
        ...
    
    def delete(self):
        """Delete the entry at current cursor position."""
        page_num, cell_idx = self.stack[-1]
        page = BTreePage(self.btree.pager, page_num)
        page.delete_cell(cell_idx)
        
        # Check if page needs rebalancing (too empty)
        if page.cell_count == 0 and page.page_number != self.root_page:
            self._rebalance_after_delete()
    
    def _rebalance_after_delete(self):
        """Rebalance after deletion: borrow from sibling or merge."""
        ...


class BTree:
    """
    Manages a B-Tree structure. Provides factory methods for cursors
    and handles tree-level operations (page splits, merges).
    """
    
    def __init__(self, pager: 'Pager', root_page: int, is_table: bool):
        self.pager = pager
        self.root_page = root_page
        self.is_table = is_table
    
    def cursor(self) -> BTreeCursor:
        return BTreeCursor(self, self.root_page)
    
    def create_leaf_page(self) -> int:
        """Create a new empty leaf page and return its page number."""
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
        """Create a new interior page."""
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
        """
        Split a full leaf page into two.
        Returns (new_page_number, middle_key, middle_payload).
        The middle entry gets promoted to the parent.
        """
        # Collect all cells with their keys
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
        
        # Sort by key (should already be sorted)
        entries.sort(key=lambda x: x[0])
        
        # Find middle
        mid = len(entries) // 2
        middle_key = entries[mid][0]
        middle_payload = entries[mid][1]
        
        # Create new page
        new_page_num = self.create_leaf_page()
        new_page = BTreePage(self.pager, new_page_num)
        
        # Redistribute cells: right half goes to new page
        page.cell_count = 0
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
    
    def split_interior_page(self, page: BTreePage) -> tuple[int, int, bytes]:
        """Split an interior page. Returns (new_page, middle_key, middle_payload)."""
        # Similar to leaf split, but handles child pointers
        ...
```


## 5. Phase 3: SQL Language (Lexer + Parser + AST)

### 5.1 Lexer (`lexer.py`)

**Purpose:** Break SQL text into tokens. SQLite's SQL is case-insensitive for keywords.

**Token Types:**
- Keywords: CREATE, TABLE, INDEX, VIEW, TRIGGER, SELECT, INSERT, UPDATE, DELETE, FROM, WHERE, JOIN, GROUP, ORDER, LIMIT, etc.
- Identifiers: IDENTIFIER, QUOTED_ID (double-quoted), BACKTICK_ID, BRACKET_ID
- Literals: INTEGER_LITERAL, FLOAT_LITERAL, STRING (single-quoted), BLOB_LITERAL (x'...')
- Operators: +, -, *, /, %, &, |, ~, <, >, =, ==, <>, !=, ||, <<, >>, ->, ->>
- Punctuation: (, ), [, ], ., ,, ;

**Lexer Implementation:**
- Scan SQL string character by character
- Categorize each token via state machine
- Handle escape sequences inside strings ('' for single quote)
- Handle line comments (--) and block comments (/* */)
- Keyword detection is case-insensitive (SELECT, select, Select all match)

**Token Structure:**
```python
@dataclass
class Token:
    type: TokenType
    value: str
    start: int      # byte offset in SQL
    end: int
    line: int
    col: int
```

### 5.2 Parser (`parser.py`)

**Design:** Recursive descent with one-token lookahead. Each grammar rule is a separate method returning AST nodes.

**Parse entry point:**
```python
class Parser:
    def __init__(self, tokens: list[Token]): ...
    def parse(self) -> list[Statement]: ...
```

**Statement dispatch (based on first token):**
- `CREATE` → `parse_create()` → delegates to `parse_create_table()`, `parse_create_index()`, `parse_create_view()`, `parse_create_trigger()`, `parse_create_virtual_table()`
- `DROP` → `parse_drop()` → delegates to `parse_drop_table()`, `parse_drop_index()`, etc.
- `ALTER` → `parse_alter()` → `RENAME TO`, `RENAME COLUMN`, `ADD COLUMN`, `DROP COLUMN`
- `SELECT` → `parse_select()` → full SELECT with JOINs, GROUP BY, HAVING, WINDOW, ORDER BY, LIMIT, compound operators
- `INSERT` → `parse_insert()` → VALUES, SELECT, DEFAULT VALUES, ON CONFLICT, RETURNING
- `UPDATE` → `parse_update()` → SET, FROM, WHERE, ORDER BY, LIMIT, RETURNING
- `DELETE` → `parse_delete()` → WHERE, ORDER BY, LIMIT, RETURNING
- `BEGIN` / `COMMIT` / `ROLLBACK` / `SAVEPOINT` / `RELEASE` → transaction statements
- `WITH` → CTE (Common Table Expression), recursive and non-recursive
- `PRAGMA` → `parse_pragma()`
- `ANALYZE` / `REINDEX` / `VACUUM` / `EXPLAIN`

**Expression parsing (operator precedence, lowest to highest):**
1. OR
2. AND
3. NOT
4. IS NULL, IS NOT NULL, IS, IS NOT
5. LIKE, GLOB, MATCH, REGEXP, IN, BETWEEN
6. || (concatenation)
7. <, <=, >, >=, =, ==, <>, !=
8. <<, >>, &, |
9. +, -
10. *, /, %
11. || (concatenation is actually here in SQLite)
12. +X, -X, ~X (unary)
13. COLLATE
14. Primary: literals, columns, function calls, CASE, CAST, subqueries, EXISTS, RAISE

**AST Nodes (defined in `ast.py`):**
- `Statement` base class
- `Select`, `Insert`, `Update`, `Delete` (DML)
- `CreateTable`, `CreateIndex`, `CreateView`, `CreateTrigger`, `CreateVirtualTable` (DDL)
- `DropTable`, `DropIndex`, `DropView`, `DropTrigger` (DDL)
- `AlterTable` with nested action types
- `Begin`, `Commit`, `Rollback`, `Savepoint`, `Release` (transactions)
- `Pragma`, `Analyze`, `Explain`
- `ColumnDef`, `TypeName`, `ColumnConstraint`, `TableConstraint`, `ForeignKey`
- `Expr` hierarchy: `Literal`, `ColumnRef`, `BinaryOp`, `UnaryOp`, `FunctionCall`, `CaseExpr`, `CastExpr`, `Subquery`, `ExistsSubquery`, `InOp`, `RowValue`, `RaiseFunction`
- Table references: `TableName`, `TableFunction`, `SubqueryTable`, `ParenthesizedTables`, `TableReference`, `JoinClause`
- `ResultColumn`, `OrderingTerm`, `WindowDef`, `WindowFrame`, `Returning`, `CTE`, `WithStatement`

### 5.3 Grammar Reference (Complete)

The full SQL grammar parsed by the parser. Each non-terminal maps to a method.

```
statement_list ::= statement (';' statement)* ';'?

statement ::= explain_stmt | ddl_stmt | dml_stmt | transaction_stmt | pragma_stmt | analyze_stmt | reindex_stmt | vacuum_stmt

ddl_stmt ::= create_table | create_index | create_view | create_trigger | create_virtual_table | drop_table | drop_index | drop_view | drop_trigger | alter_table

dml_stmt ::= select_stmt | insert_stmt | update_stmt | delete_stmt

create_table ::= CREATE (TEMP|TEMPORARY)? TABLE (IF NOT EXISTS)? (schema.)?name '(' column_def (',' column_def)* (',' table_constraint)* ')' (WITHOUT ROWID)? (STRICT)?
              | CREATE (TEMP|TEMPORARY)? TABLE (IF NOT EXISTS)? (schema.)?name AS select_stmt

column_def ::= name type_name? column_constraint*

type_name ::= name ('(' signed_number ')' | '(' signed_number ',' signed_number ')')?

column_constraint ::= (CONSTRAINT name)? (
    PRIMARY KEY (ASC|DESC)? conflict_clause? (AUTOINCREMENT)?
  | NOT NULL conflict_clause?
  | UNIQUE conflict_clause?
  | CHECK '(' expr ')'
  | DEFAULT (signed_number | literal_value | '(' expr ')' | CURRENT_TIME | CURRENT_DATE | CURRENT_TIMESTAMP)
  | COLLATE collation_name
  | REFERENCES foreign_table '(' col (',' col)* ')' foreign_key_clause*
  | GENERATED ALWAYS? AS '(' expr ')' (STORED|VIRTUAL)?
  | AS '(' expr ')' (STORED|VIRTUAL)?
)

table_constraint ::= (CONSTRAINT name)? (
    PRIMARY KEY '(' indexed_column (',' indexed_column)* ')' conflict_clause?
  | UNIQUE '(' indexed_column (',' indexed_column)* ')' conflict_clause?
  | CHECK '(' expr ')'
  | FOREIGN KEY '(' col (',' col)* ')' REFERENCES foreign_table '(' col (',' col)* ')' foreign_key_clause*
)

select_stmt ::= (WITH (RECURSIVE)? cte_table (',' cte_table)*)?
                SELECT (DISTINCT|ALL)? result_column (',' result_column)*
                (FROM table_or_subquery (',' table_or_subquery)*)?
                (WHERE expr)?
                (GROUP BY expr (',' expr)* (HAVING expr)?)?
                (WINDOW window_name AS window_def (',' ...)*)?
                (compound_op select_stmt)?
                (ORDER BY ordering_term (',' ordering_term)*)?
                (LIMIT expr (OFFSET expr)?)?
                (FOR UPDATE)?

compound_op ::= UNION | INTERSECT | EXCEPT (ALL)?

insert_stmt ::= (WITH (RECURSIVE)? cte_table (',' cte_table)*)?
                INSERT (OR (ROLLBACK|ABORT|FAIL|IGNORE|REPLACE))?
                INTO (schema.)?name (AS alias)? '(' col (',' col)* ')'
                (VALUES '(' expr (',' expr)* ')' (',' '(' expr (',' expr)* ')')*
               | select_stmt
               | DEFAULT VALUES)
                (ON CONFLICT '(' col (',' col)* ')' (WHERE expr)? DO
                  (NOTHING | UPDATE SET set_clause (',' set_clause)* (WHERE expr)?))?
                (RETURNING result_column (',' result_column)*)?

update_stmt ::= (WITH (RECURSIVE)? cte_table (',' cte_table)*)?
                UPDATE (OR (ROLLBACK|ABORT|FAIL|IGNORE|REPLACE))?
                (schema.)?name (AS alias)?
                SET set_clause (',' set_clause)*
                (FROM table_or_subquery (',' table_or_subquery)*)?
                (WHERE expr)?
                (ORDER BY ordering_term (',' ordering_term)*)?
                (LIMIT expr (OFFSET expr)?)?
                (RETURNING result_column (',' result_column)*)?

delete_stmt ::= (WITH (RECURSIVE)? cte_table (',' cte_table)*)?
                DELETE FROM (schema.)?name (AS alias)?
                (WHERE expr)?
                (ORDER BY ordering_term (',' ordering_term)*)?
                (LIMIT expr (OFFSET expr)?)?
                (RETURNING result_column (',' result_column)*)?

expr ::= expr OR expr
       | expr AND expr
       | NOT expr
       | expr (IS NULL | IS NOT NULL | NOTNULL | IS | IS NOT) expr
       | expr (MATCH | REGEXP | LIKE | GLOB) expr (ESCAPE expr)?
       | expr (IN | NOT IN) '(' expr (',' expr)* ')' | select_stmt | table_name
       | expr BETWEEN expr AND expr
       | expr '||' expr
       | expr ('<' | '<=' | '>' | '>=' | '=' | '==' | '<>' | '!=') expr
       | expr ('<<' | '>>' | '&' | '|') expr
       | expr ('+' | '-') expr
       | expr ('*' | '/' | '%') expr
       | ('+' | '-' | '~') expr
       | expr COLLATE collation_name
       | literal_value
       | column_ref
       | function_name '(' (DISTINCT)? (expr (',' expr)* | '*') ')' (FILTER '(' WHERE expr ')')? (OVER window_def)?
       | '(' expr ')'
       | '(' select_stmt ')'
       | EXISTS '(' select_stmt ')'
       | CASE expr? (WHEN expr THEN expr)+ (ELSE expr)? END
       | CAST '(' expr AS type_name ')'
       | expr '->' expr
       | expr '->>' expr
       | RAISE '(' IGNORE | (ROLLBACK|ABORT|FAIL) ',' error_msg ')'
```

## 6. Phase 4: Bytecode Compiler & Virtual Machine

### 6.1 Opcode Definitions (`opcode.py`)

**Design:** Register-based virtual machine with ~200 opcodes, each operating on typed registers. Modeled closely on SQLite's VDBE (Virtual Database Engine).

**Instruction Format:**
```python
@dataclass
class Instruction:
    opcode: str      # mnemonic name
    P1: int = 0      # primary operand (cursor, register, jump addr)
    P2: int = 0      # secondary operand (jump addr, register, value)
    P3: int = 0      # tertiary operand (count, register)
    P4: Any = None   # fourth operand (string, function object, blob)
    P5: int = 0      # flags (8-bit)
```

**Opcode Categories:**

**Init / Halt:**
- `Init` (P1=start_reg, P2=start_addr) — initialize VM, jump to P2
- `Halt` (P1=err_code, P4=err_msg) — stop execution

**Cursor Operations:**
- `OpenRead` (P1=cursor, P2=root_page, P3=n_col, P4=index_info) — open B-Tree for reading
- `OpenWrite` — same, but allows modifications
- `OpenEphemeral` (P1=cursor, P2=n_cols) — create temp B-Tree
- `OpenPseudo` (P1=cursor) — pseudo-cursor for single row
- `OpenAutoindex` (P1=cursor, P2=n_key_cols) — automatic index for join
- `OpenDup` (P1=dest_cursor, P2=src_cursor) — duplicate cursor
- `Close` (P1=cursor) — close cursor
- `Rewind` (P1=cursor, P2=addr_if_empty) — position at first row
- `Last` (P1=cursor) — position at last row
- `Next` (P1=cursor, P2=addr_loop) — advance cursor, jump if more rows
- `Prev` (P1=cursor, P2=addr_loop) — previous row
- `SeekGT` / `SeekGE` / `SeekLT` / `SeekLE` (P1=cursor, P2=addr_notfound, P3=key_reg) — index seek
- `SeekRowid` (P1=cursor, P2=addr_notfound, P3=rowid_reg) — exact rowid seek
- `IdxSeekGT` / `IdxSeekGE` / `IdxSeekLT` / `IdxSeekLE` — index cursor seeks
- `IdxInsert` (P1=cursor, P2=key_reg, P3=flags) — insert into index
- `IdxDelete` (P1=cursor, P2=key_reg) — delete from index
- `IdxRowid` (P1=cursor, P2=dest_reg) — read rowid from index entry

**Record Operations:**
- `MakeRecord` (P1=first_reg, P2=n_cols, P3=dest_reg) — serialize registers into record blob
- `Column` (P1=cursor, P2=col_idx, P3=dest_reg) — extract column from current row
- `Affinity` (P1=first_reg, P2=n_cols, P4=affinity_str) — apply type affinity
- `TypeCheck` — verify types for STRICT tables
- `Cast` (P1=reg, P2=affinity, P3=dest) — type cast

**Comparison / Flow Control:**
- `Eq` / `Ne` / `Lt` / `Le` / `Gt` / `Ge` (P1=left_reg, P2=addr_if_true, P3=right_reg) — compare and branch
- `IsNull` (P1=reg, P2=addr) — branch if NULL
- `NotNull` (P1=reg, P2=addr) — branch if not NULL
- `Compare` (P1=left_start, P2=right_start, P3=n_fields) — compare register sets, set compare_flags
- `If` / `IfNot` (P1=reg, P2=addr) — branch on truthiness
- `IfNotZero` (P1=reg, P2=addr, P3=decrement) — decrement and branch if not zero
- `IfZero` / `IfPos` / `IfNeg` — numeric conditional branches
- `Once` (P1=addr) — execute only once per program run
- `Goto` (P1=addr) — unconditional jump
- `Gosub` (P1=addr, P2=return_reg) — subroutine call
- `Return` — return from subroutine
- `Yield` (P1=status_reg) — yield execution (for progress callbacks)

**Register Management:**
- `MemNull` (P1=reg) — set to NULL
- `MemInt` (P1=reg, P2=value) — set to integer
- `MemReal` (P1=reg, P2=bits) — set to float (from IEEE 754 bits)
- `MemStr` (P1=reg, P4=str) — set to string
- `MemMove` (P1=dest, P2=src) — move (src becomes NULL)
- `MemCopy` / `SCopy` — copy value
- `Null` / `Integer` / `Real` / `String` / `Blob` — set register to immediate value

**Aggregation:**
- `AggStep` (P1=func_idx, P2=first_arg, P3=n_args, P4=acc_reg) — feed args to aggregate
- `AggFinal` (P1=func_idx, P2=acc_reg, P3=dest_reg) — finalize and get result
- `AggValue` — get partial aggregate value
- `AggInvert` — remove last step (for window frames)
- `AggReset` — reset accumulator

**Sorting:**
- `SorterOpen` (P1=cursor, P2=n_fields) — open external sorter
- `SorterInsert` (P1=cursor, P2=record_reg) — insert into sorter
- `SorterSort` (P1=cursor, P2=addr) — sort and prepare to read
- `SorterData` (P1=cursor, P2=dest_reg) — read sorted record
- `SorterNext` (P1=cursor, P2=addr) — advance sorter

**Transaction:**
- `Transaction` (P1=write_flag) — begin transaction
- `ReadCookie` (P1=cookie_offset, P2=dest_reg) — read header cookie
- `SetCookie` (P1=cookie_offset, P2=reg) — write header cookie
- `VerifyCookie` (P1=expected_schema) — verify schema unchanged
- `ParseSchema` (P1=flags) — (re)parse sqlite_schema table
- `Savepoint` / `Release` / `RollbackTo` — savepoint management

**I/O (Result Output):**
- `ResultRow` (P1=first_reg, P2=n_cols) — emit result row
- `ResultColumn` (P1=reg) — add column to current row

**Data Modification:**
- `Insert` (P1=cursor, P2=record_reg, P3=rowid_reg) — insert row
- `Delete` (P1=cursor) — delete current row
- `NewRowid` (P1=cursor, P2=addr_full, P3=dest_reg) — generate new rowid
- `Rowid` (P1=cursor, P2=dest_reg) — read rowid of current row
- `RowData` (P1=cursor, P2=dest_reg) — read record payload
- `CreateTable` / `CreateIndex` / `DropTable` / `DropIndex` — DDL operations
- `Clear` (P1=cursor) — delete all rows
- `Count` (P1=cursor, P2=dest_reg) — COUNT(*)

**Functions:**
- `Function` (P1=first_arg, P2=n_args, P3=dest, P4=func_obj) — call registered function
- `Function0` — same, but known to have no side effects
- `Like` / `Glob` / `Regexp` — pattern matching
- Math opcodes: `Add`, `Subtract`, `Multiply`, `Divide`, `Remainder`, `Concat`, `BitAnd`, `BitOr`, `ShiftLeft`, `ShiftRight`
- String opcodes: `Length`, `Substr`, `Instr`, `ReplaceFunc`, `Trim`, `LTrim`, `RTrim`, `Upper`, `Lower`, `Hex`, `Quote`, `Unicode`, `Char`
- Numeric opcodes: `AbsValue`, `Round`, `Ceil`, `Floor`, `Trunc`, `Coalesce`, `IfNull`, `NullIf`
- Info opcodes: `Typeof`, `LastInsertRowid`, `Changes`
- System: `SystemFunc`, `PtTm` (date/time)

### 6.2 Query Compiler (`compile.py`)

**Purpose:** Walk the AST and emit VDBE bytecode.

**Compiler Design:**
```python
class Compiler:
    def __init__(self, schema, db):
        self.schema = schema
        self.db = db
        self.instructions: list[Instruction] = []
        self.labels: dict[str, int] = {}
        self.pending_labels: dict[str, list[int]] = {}
        self.next_register = 0
        self.next_cursor = 0
        # Pre-allocated registers for constants
        self.reg_zero = self.alloc_reg()  # holds integer 0
        self.reg_one = self.alloc_reg()   # holds integer 1
        self.reg_null = self.alloc_reg()  # holds NULL

    def compile(self, statement: Statement) -> list[Instruction]:
        self.instructions = []
        if isinstance(statement, Select):
            self._compile_select(statement)
        elif isinstance(statement, Insert):
            self._compile_insert(statement)
        elif isinstance(statement, Update):
            self._compile_update(statement)
        elif isinstance(statement, Delete):
            self._compile_delete(statement)
        elif isinstance(statement, CreateTable):
            self._compile_create_table(statement)
        elif isinstance(statement, CreateIndex):
            self._compile_create_index(statement)
        elif isinstance(statement, DropTable):
            self._compile_drop_table(statement)
        # ... etc
        self.emit('Halt')
        self._resolve_labels()
        return self.instructions
```

**SELECT Compilation Strategy:**

1. **Single-table without WHERE** → Rewind → loop Next → Column → ResultRow
2. **Single-table with equality WHERE** → SeekRowid or IndexSeek → Column → ResultRow
3. **Single-table with range WHERE** → SeekGE → Next loop with Compare → ResultRow
4. **JOINs** → nested loops; outer table first (most restrictive), inner second; auto-index on join column if no index exists
5. **ORDER BY** → if index provides order, use it; otherwise collect in Sorter, sort, emit
6. **GROUP BY** → collect in ephemeral B-Tree keyed by group columns; aggregate per group
7. **DISTINCT** → collect in ephemeral uniqueness B-Tree; deduplicate
8. **LIMIT/OFFSET** → counter registers; decrement, skip, stop
9. **UNION/INTERSECT/EXCEPT** → ephemeral B-Trees for union and dedup logic
10. **Subqueries** → executed as subprograms; result stored in register
11. **Window functions** → partition in sorter, evaluate per frame

**INSERT Compilation Strategy:**
- OpenWrite on table and all indexes
- For each row of VALUES: evaluate expressions, fill defaults, generate rowid, MakeRecord, Insert
- Update each index (IdxInsert)
- Handle ON CONFLICT: check constraint violation, route to DO NOTHING or DO UPDATE
- Handle RETURNING: after insert, emit columns of inserted row

**UPDATE Compilation Strategy:**
- OpenWrite on table and indexes
- For each matching row: read current values, evaluate SET expressions
- Delete old index entries (IdxDelete)
- Delete old row (Delete)
- Insert new row with updated values (Insert)
- Insert new index entries (IdxInsert)

**DELETE Compilation Strategy:**
- OpenWrite on table
- For each matching row: delete from all indexes, delete from table

**Expression Compilation:**
Each expression type compiles to bytecode that leaves its value in a register:
- `Literal` → `Integer`/`Real`/`String`/`Null`/`Blob`
- `ColumnRef` → `Column(cursor, col_idx, dest)` (uses current scan cursor)
- `BinaryOp` → compile left and right, then operator opcode (e.g., `Add`)
- `UnaryOp` → compile operand, then unary opcode
- `FunctionCall` → compile args, then `Function` opcode
- `CaseExpr` → `If`/`Goto` chain evaluating WHEN clauses
- `CastExpr` → compile inner expr, then `Cast`

### 6.3 Virtual Machine (`vm.py`)

**Purpose:** Execute compiled VDBE programs.

**Core Register System:**
```python
class Register:
    type: str  # 'NULL', 'INT', 'REAL', 'TEXT', 'BLOB'
    value: Any
```

**Core Data Structures:**
```python
class Cursor:
    btree: BTree       # underlying B-Tree
    cursor: BTreeCursor
    is_writable: bool
    is_open: bool
    eof: bool
    row: list[Register]  # cached decoded row

class VM:
    program: list[Instruction]
    pc: int
    registers: dict[int, Register]
    cursors: dict[int, Cursor]
    result_rows: list[list]
    error: str | None
    last_rowid: int
    changes: int
    compare_flags: int          # -1, 0, 1 from last Compare
    agg_accumulators: dict      # for aggregate functions
    sub_return_stack: list[int] # for Gosub/Return
```

**Execution Loop:**
```python
def run(self) -> list[list]:
    while self.pc < len(self.program) and self.error is None:
        self.step()
    if self.error:
        raise DatabaseError(self.error)
    return self.result_rows
```

Each `step()` reads the instruction at program counter, increments pc, dispatches to the handler method for that opcode. Handlers are organized as `_op_OPCODENAME` methods.

**Key Opcode Implementations:**

**Init:** Set up registers, jump to program start address.

**Halt:** Set error if P1 != 0, stop execution.

**OpenRead/OpenWrite:** Create a BTree instance with the given root page, wrap in Cursor, store in cursors[P1].

**OpenEphemeral:** Create a MemoryPager + BTree for temporary tables (sorting, grouping, distinct).

**Rewind:** Call BTreeCursor.first(). If EOF and P2 > 0, jump to P2 (skip loop).

**Next/Prev:** Advance cursor. If not EOF and P2 > 0, jump back to P2 (loop continuation).

**SeekRowid:** Call BTreeCursor.seek(P3 value). If not found, jump to P2.

**Column:** Extract column at index P2 from current cursor row. Decode record payload, deserialize into Register.

**MakeRecord:** Read consecutive registers, serialize to record blob using Record class.

**ResultRow:** Read consecutive registers, append as list to result_rows.

**Goto:** Set pc = P1 (or P2 if P1 == 0).

**If/IfNot:** Check register truthiness. NULL, 0, empty string/blob are falsy. Jump if condition met.

**Eq/Ne/Lt/Le/Gt/Ge:** Compare two registers using SQLite's type ordering (NULL < INT/REAL < TEXT < BLOB, with appropriate casting). Jump to P2 if comparison is true.

**Insert:** Build record, get rowid (auto-generate if needed), call BTreeCursor.insert().

**Delete:** Call BTreeCursor.delete() at current position.

**NewRowid:** Scan to find max rowid in table, return max + 1.

**Function:** Look up function by name from registry, call with arguments from registers, store result.

**AggStep/AggFinal:** Collect argument arrays per function ID; on finalize, call the aggregate function's finalize method.

**Affinity:** Apply SQLite affinity transformation rules per column. For each register, convert between INT, REAL, TEXT based on declared column affinity.

**SQLite Type Sorting Order (for comparisons):**
1. NULL values come first (all equal to each other)
2. INT and REAL values come next (numerically sorted)
3. TEXT values come after (sorted by collation sequence)
4. BLOB values come last (sorted by memcmp)

**Boolean Conversion:**
- INT 0 → false
- NULL → false
- Empty TEXT/BLOB → false
- Everything else → true

### 6.4 Query Optimizer (embedded in compiler)

**Index Selection Algorithm:**
```python
def _choose_index(self, table_def, where_expr):
    """
    1. Walk WHERE expression tree to extract column comparisons
    2. For each index on the table, count how many leading columns
       are used with equality or range conditions
    3. Choose index with highest coverage
    4. Prefer UNIQUE indexes for equality matches
    5. If multiple indexes tie, prefer one with ORDER BY coverage
    """
    # Extract column references from WHERE
    # Classify each reference as equality ('='), range ('<', '>', 'BETWEEN'),
    #   IN-list, or unsupported
    # For each index, count matching leading columns
    # Return best index or None for full scan
```

**Join Ordering:**
- For N tables, estimate row counts after applying local WHERE conditions
- Order tables by increasing estimated row count (most selective first)
- For each pair, if no join index exists, plan to auto-create an ephemeral index on the inner table's join column

**Cost Estimation:**
- Full table scan cost = estimated rows in table
- Index equality seek cost = log2(pages_in_index) + 1 (page read)
- Index range scan cost = estimated matching rows
- Use ANALYZE stats (sqlite_stat1) if available for precise estimates

### 6.5 EXPLAIN Support

When EXPLAIN is prepended to a statement, instead of executing the program, the VM outputs the program listing as a result set. Each instruction is a row with columns: addr, opcode, P1, P2, P3, P4, P5, comment.

For EXPLAIN QUERY PLAN, the compiler annotates the program with comments describing the plan (SCAN TABLE, SEARCH TABLE USING INDEX, etc.) and outputs a simplified plan view.

## 7. Phase 5: Schema & Catalog

### 7.1 Schema Manager (`schema.py`)

**Purpose:** Manage database metadata stored in the `sqlite_schema` table.

**sqlite_schema Table Layout:**
```
Column    Type      Description
type      TEXT      'table', 'index', 'view', 'trigger'
name      TEXT      Object name (unique per schema)
tbl_name  TEXT      Associated table name (for indexes/triggers/views)
rootpage  INTEGER   Root B-Tree page number (0 for views/triggers)
sql       TEXT      Original CREATE statement
```

The schema table is stored as a regular B-Tree with root page 1 (page 1 contains both the database header and the schema B-Tree root).

**Schema Manager Implementation:**
```python
class Schema:
    def __init__(self, pager):
        self.pager = pager
        self.tables: dict[str, TableDef] = {}
        self.indexes: dict[str, IndexDef] = {}
        self.views: dict[str, ViewDef] = {}
        self.triggers: dict[str, TriggerDef] = {}
        self.collations: dict[str, Collation] = {}
        self.schema_version = 0
        self.schema_cookie = 0
    
    def load(self):
        """Read and parse sqlite_schema B-Tree, populate metadata."""
        btree = BTree(self.pager, 1, is_table=True)
        cursor = btree.cursor()
        cursor.first()
        while not cursor.eof:
            payload = cursor.current_payload()
            record, _ = Record.decode(payload)
            values = record.get_values()
            type_, name, tbl_name, rootpage, sql = values
            self._register_object(type_, name, tbl_name, rootpage, sql)
            cursor.next()
    
    def _register_object(self, type_, name, tbl_name, rootpage, sql):
        if type_ == 'table':
            self.tables[name] = self._parse_create_table(name, rootpage, sql)
        elif type_ == 'index':
            self.indexes[name] = self._parse_create_index(name, tbl_name, rootpage, sql)
        elif type_ == 'view':
            self.views[name] = ViewDef(name, sql, self._extract_select(sql))
        elif type_ == 'trigger':
            self.triggers[name] = self._parse_create_trigger(name, tbl_name, sql)
    
    def _parse_create_table(self, name, rootpage, sql) -> TableDef:
        """Parse the CREATE TABLE SQL string back into ColumnDef list + constraints."""
        tokens = Lexer(sql).tokenize()
        parser = Parser(tokens)
        stmt = parser.parse_create_table(False)  # parse as non-temp
        columns = []
        for col_def in stmt.columns:
            affinity = self._determine_affinity(col_def.type_name)
            columns.append(ColumnDef(
                name=col_def.name,
                type_name=col_def.type_name,
                affinity=affinity,
                not_null=self._has_constraint(col_def, ConstraintType.NOT_NULL),
                primary_key=self._has_constraint(col_def, ConstraintType.PRIMARY_KEY),
                unique=self._has_constraint(col_def, ConstraintType.UNIQUE),
                default_value=self._get_default(col_def),
                auto_increment=self._has_autoinc(col_def),
                collation=self._get_collation(col_def),
            ))
        return TableDef(
            name=name, root_page=rootpage, columns=columns,
            constraints=stmt.constraints,
            without_rowid=stmt.without_rowid, strict=stmt.strict,
            sql=sql
        )
    
    def save(self):
        """Write current schema back to sqlite_schema (on DDL changes)."""
        # Open sqlite_schema for writing
        btree = BTree(self.pager, 1, is_table=True)
        # Clear existing entries
        # Insert each object
        for table in self.tables.values():
            self._insert_schema_entry(btree, 'table', table.name, table.name,
                                     table.root_page, table.sql)
        # ... similar for indexes, views, triggers
    
    def _determine_affinity(self, type_name: TypeName | None) -> int:
        """SQLite type affinity rules (5 types)."""
        if type_name is None or not type_name.name:
            return AFFINITY_BLOB
        name = type_name.name.upper()
        if any(kw in name for kw in ('INT', 'TINY', 'SMALL', 'MEDIUM', 'BIG',
                                      'UNSIGNED', 'BOOLEAN', 'BIT')):
            return AFFINITY_INTEGER
        if any(kw in name for kw in ('REAL', 'FLOAT', 'DOUBLE', 'NUMERIC', 'DECIMAL')):
            if name == 'NUMERIC' or name == 'DECIMAL':
                return AFFINITY_NUMERIC
            return AFFINITY_REAL
        if any(kw in name for kw in ('CHAR', 'CLOB', 'TEXT', 'VARCHAR', 'VARYING',
                                      'NCHAR', 'NVARCHAR', 'NATIONAL', 'DATE', 'DATETIME')):
            return AFFINITY_TEXT
        if name == 'BLOB' or not name:
            return AFFINITY_BLOB
        if name in ('NUMERIC', 'DECIMAL', 'BOOLEAN', 'DATE', 'DATETIME'):
            return AFFINITY_NUMERIC
        return AFFINITY_BLOB  # fallback
```

**TableDef Data Structure:**
```python
class TableDef:
    name: str
    root_page: int
    columns: list[ColumnDef]
    constraints: list[TableConstraint]
    indexes: list[IndexRef]          # indexes on this table
    foreign_keys: list[ForeignKey]
    without_rowid: bool
    strict: bool
    sql: str
    
    def has_autoinc(self) -> bool: ...
    def primary_key_columns(self) -> list[str]: ...
    def column_index(self, name: str) -> int: ...

class ColumnDef:
    name: str
    type_name: TypeName | None
    affinity: int                    # INTEGER, REAL, NUMERIC, TEXT, BLOB
    not_null: bool
    primary_key: bool
    unique: bool
    default_value: Any | None
    auto_increment: bool
    collation: str | None
    is_generated: bool
    generated_expr: Expr | None
    generated_type: str | None       # STORED or VIRTUAL

class IndexDef:
    name: str
    table_name: str
    root_page: int
    columns: list[IndexedColumnDef]
    unique: bool
    partial: bool
    partial_where: Expr | None
    sql: str

class IndexedColumnDef:
    name: str
    collation: str | None
    order: str                       # ASC or DESC
    expr: Expr | None                # for functional indexes
```

### 7.2 Collation Sequences

SQLite supports three built-in collations:
- **BINARY** — memcmp byte-by-byte (default for all columns)
- **NOCASE** — ASCII case-insensitive (A-Z == a-z)
- **RTRIM** — like BINARY but ignores trailing spaces

User-defined collations can be registered:
```python
class Collation:
    def __init__(self, name: str, callable):
        self.name = name
        self.func = callable  # (str_a, str_b) -> -1, 0, 1
    
    def compare(self, a: str, b: str) -> int:
        return self.func(a, b)
```

Collation is used in:
- Comparison expressions (column COLLATE collation_name)
- ORDER BY clause
- GROUP BY clause
- Index key ordering (index creation stores collation per column)

### 7.3 Schema Versioning

When schema changes (CREATE, DROP, ALTER), increment `schema_cookie` in the database header. The VM's `VerifyCookie` instruction checks that the schema hasn't changed since compilation; if it has, the program is aborted and recompiled.

---

## 8. Phase 6: Transaction & Concurrency

### 8.1 Transaction Manager (`transaction.py`)

**Purpose:** Manage ACID transactions, savepoints, and concurrent access.

**Transaction States:**
```python
class TransactionState(Enum):
    NONE = 0       # No active transaction
    READ = 1       # Read transaction (SHARED lock)
    WRITE = 2      # Write transaction (RESERVED + PENDING + EXCLUSIVE)
    READ_UNCOMMITTED = 3  # Read uncommitted mode
```

**Lock Protocol (5-state):**
1. **UNLOCKED** — No lock held; no operations permitted
2. **SHARED** — Read lock; multiple readers allowed simultaneously
3. **RESERVED** — Write lock in preparation; existing readers continue; only one writer may reserve
4. **PENDING** — Writer waiting for readers to finish; new readers blocked
5. **EXCLUSIVE** — Exclusive write lock; no other readers or writers; used during commit

**Lock Lifecycle:**
```
UNLOCKED → SHARED (on BEGIN or first SELECT)
SHARED → RESERVED (on first write operation)
RESERVED → PENDING (when ready to commit, waiting for readers)
PENDING → EXCLUSIVE (when all readers finish)
EXCLUSIVE → UNLOCKED or SHARED (after commit/rollback)
```

**Transaction Manager Implementation:**
```python
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
        self.deferred_fk_ops: list[FKOperation] = []
    
    def begin(self, mode=None):
        """Begin transaction: DEFERRED (default), IMMEDIATE, or EXCLUSIVE."""
        if self.state != TransactionState.NONE:
            return  # nested transaction handled by savepoints
        
        if mode == 'EXCLUSIVE':
            self.vfs.lock(self.handle, LOCK_EXCLUSIVE)
        elif mode == 'IMMEDIATE':
            self.vfs.lock(self.handle, LOCK_RESERVED)
        else:  # DEFERRED
            self.vfs.lock(self.handle, LOCK_SHARED)
        
        if self.journal_mode != JournalMode.OFF:
            self.pager.begin_journal()
        
        self.state = TransactionState.READ
    
    def commit(self):
        """Commit the current transaction atomically."""
        if self.state == TransactionState.NONE:
            return
        
        # Check FK constraints if enabled
        if self.fk_constraints_enabled and not self.defer_fk_constraints:
            self._check_deferred_fk()
        
        if self.state == TransactionState.WRITE:
            # Upgrade lock to EXCLUSIVE
            self.vfs.lock(self.handle, LOCK_EXCLUSIVE)
            # Flush and sync
            self.pager.flush_journal()
            self.pager.commit_journal()
        
        self.vfs.unlock(self.handle, LOCK_SHARED)
        self.state = TransactionState.NONE
    
    def rollback(self):
        """Rollback the current transaction."""
        if self.state == TransactionState.NONE:
            return
        
        if self.state == TransactionState.WRITE:
            self.pager.rollback_journal()
        
        self.vfs.unlock(self.handle, LOCK_NONE)
        self.state = TransactionState.NONE
        self.deferred_fk_ops.clear()
    
    def savepoint(self, name=None):
        """Create a savepoint (nested transaction)."""
        sp = Savepoint(name, self.state, self.pager.savepoint_state())
        self.savepoint_stack.append(sp)
    
    def release(self, name=None):
        """Release a savepoint (keep changes)."""
        while self.savepoint_stack:
            sp = self.savepoint_stack.pop()
            if sp.name == name:
                break
    
    def rollback_to(self, name=None):
        """Rollback to a savepoint (undo changes since savepoint)."""
        while self.savepoint_stack:
            sp = self.savepoint_stack.pop()
            self.pager.rollback_to_savepoint(sp)
            if sp.name == name:
                break
    
    def _check_deferred_fk(self):
        """Check all deferred foreign key operations."""
        for fk_op in self.deferred_fk_ops:
            if not self._check_fk_operation(fk_op):
                raise ConstraintForeignKeyError(f"FOREIGN KEY constraint failed")
        self.deferred_fk_ops.clear()
```

### 8.2 Savepoint Protocol

Savepoints use a copy-on-write mechanism:
1. On savepoint creation, record current pager state
2. On rollback to savepoint, restore page before-images from journal for pages modified after savepoint
3. On release, merge changes into parent transaction

### 8.3 Foreign Key Enforcement

Foreign key constraints are checked at the end of each statement (immediate mode) or at commit time (deferred mode).

**Check logic:**
```python
def check_fk_on_insert(self, fk, child_cursor, child_values, child_table):
    """After inserting into child table, verify referenced key exists in parent."""
    # Extract foreign key column values from child row
    child_keys = [child_values[col_idx] for col_idx in fk.child_columns]
    # Look for matching row in parent table
    parent_btree = BTree(self.pager, fk.parent_table.root_page, True)
    parent_cursor = parent_btree.cursor()
    # Search for parent key match
    found = parent_cursor.seek(child_keys[0])  # simplified: multi-column needs index scan
    if not found:
        raise ConstraintForeignKeyError(f"FOREIGN KEY constraint failed")
```

**CASCADE / SET NULL / SET DEFAULT / RESTRICT / NO ACTION:**
- `CASCADE`: when parent key deleted/updated, cascade to child rows
- `SET NULL`: set child FK columns to NULL
- `SET DEFAULT`: set child FK columns to their default values
- `RESTRICT`: prevent parent modification if child references exist
- `NO ACTION`: defer check to transaction end (default)

### 8.4 Concurrent Access

For file-level locking, use OS-specific advisory locks via `msvcrt.locking()` on Windows or `fcntl.flock()` / `fcntl.lockf()` on Unix.

**Lock compatibility matrix:**
```
             NONE   SHARED   RESERVED   PENDING   EXCLUSIVE
NONE         ✓      ✓        ✓          ✓         ✓
SHARED       ✓      ✓        ✓          ✗         ✗
RESERVED     ✓      ✓        ✗          ✗         ✗
PENDING      ✓      ✗        ✗          ✗         ✗
EXCLUSIVE    ✓      ✗        ✗          ✗         ✗
```

The busy handler (configurable via `busy_timeout` pragma) retries failed lock acquisitions up to the timeout period. Implement with exponential backoff.

## 9. Phase 7: Full SQL Feature Set

### 9.1 Built-in Functions

**Aggregate Functions (in `functions/aggregate.py`):**

Each aggregate implements a class with `step(args)` and `finalize()` methods.

```python
class AggregateFunction:
    """Base class for all aggregate functions."""
    def __init__(self):
        self.reset()
    
    def step(self, *args):
        """Called for each row in the group."""
        raise NotImplementedError
    
    def finalize(self):
        """Called after all rows processed. Returns the aggregate result."""
        raise NotImplementedError
    
    def reset(self):
        """Reset accumulator state."""
        raise NotImplementedError

class Count(AggregateFunction):
    def reset(self): self.count = 0
    def step(self, *args):
        if len(args) == 0 or args[0] is not None or args[0] != 0:
            self.count += 1  # COUNT(*) or COUNT(col)
    def finalize(self): return self.count

class Sum(AggregateFunction):
    def reset(self): self.total = None
    def step(self, *args):
        if args[0] is not None:
            self.total = (self.total or 0) + args[0]
    def finalize(self): return self.total

class Avg(AggregateFunction):
    def reset(self): self.total = 0.0; self.count = 0
    def step(self, *args):
        if args[0] is not None:
            self.total += float(args[0])
            self.count += 1
    def finalize(self):
        return self.total / self.count if self.count > 0 else None

class Min(AggregateFunction):
    def reset(self): self.min = None
    def step(self, *args):
        if args[0] is not None:
            if self.min is None or args[0] < self.min:
                self.min = args[0]
    def finalize(self): return self.min

class Max(AggregateFunction):
    def reset(self): self.max = None
    def step(self, *args):
        if args[0] is not None:
            if self.max is None or args[0] > self.max:
                self.max = args[0]
    def finalize(self): return self.max

class GroupConcat(AggregateFunction):
    def reset(self): self.values = []
    def step(self, *args):
        val = args[0]
        if val is not None:
            self.values.append(str(val))
    def finalize(self):
        sep = ','  # default separator
        return sep.join(self.values)

class Total(AggregateFunction):
    """Like SUM but returns 0.0 for no rows (instead of NULL)."""
    def reset(self): self.total = 0.0
    def step(self, *args):
        if args[0] is not None:
            self.total += float(args[0])
    def finalize(self): return self.total
```

**Aggregate registration:**
```python
AGGREGATE_FUNCTIONS = {
    'COUNT': Count,
    'SUM': Sum,
    'AVG': Avg,
    'MIN': Min,
    'MAX': Max,
    'GROUP_CONCAT': GroupConcat,
    'TOTAL': Total,
}
```

**Scalar Functions (in `functions/scalar.py`):**

Each scalar function is a plain Python callable registered by name.

**String functions:**
- `length(X)` → len(str(X)) or len(X) for BLOB; NULL if X is NULL
- `substr(X, Y, Z)`, `substring(X, Y, Z)` → `str(X)[Y-1:Y-1+Z]` (SQLite is 1-indexed)
- `replace(X, Y, Z)` → `str(X).replace(Y, Z, 1)` (only first occurrence!)
- `trim(X, Y)`, `ltrim(X, Y)`, `rtrim(X, Y)` → strip characters in Y (default: spaces)
- `upper(X)` → `str(X).upper()`
- `lower(X)` → `str(X).lower()`
- `hex(X)` → `X.hex()` for BLOB, or encode string to bytes then hex
- `quote(X)` → SQL-quoted string literal
- `unicode(X)` → `ord(str(X)[0])`
- `char(X1, X2, ...)` → `''.join(chr(x) for x in args)`
- `instr(X, Y)` → `str(X).find(str(Y)) + 1` (0 if not found)
- `length(X)` → `len(str(X))` or `len(X)` for BLOB
- `sqlite_version()` → `'3.45.0'`
- `typeof(X)` → type name string ('null', 'integer', 'real', 'text', 'blob')
- `coalesce(X, Y, ...)` → first non-NULL arg
- `ifnull(X, Y)` → X if not NULL else Y
- `nullif(X, Y)` → NULL if X == Y else X

**Numeric functions:**
- `abs(X)` → abs
- `round(X, Y)` → round with Y decimal places
- `ceil(X)` / `ceiling(X)` → math.ceil
- `floor(X)` → math.floor
- `trunc(X)` → int(X) truncation
- `random()` → random integer
- `randomblob(N)` → random N bytes
- `zeroblob(N)` → N zero bytes

**Math functions (`functions/math.py`):**
- `acos(X)`, `acosh(X)`, `asin(X)`, `asinh(X)`, `atan(X)`, `atanh(X)`, `atan2(Y, X)`
- `cos(X)`, `cosh(X)`, `sin(X)`, `sinh(X)`, `tan(X)`, `tanh(X)`
- `degrees(X)`, `radians(X)`
- `exp(X)`, `ln(X)`, `log(X)`, `log10(X)`, `log2(X)`
- `pi()` → math.pi
- `pow(X, Y)`, `power(X, Y)` → X ** Y
- `sqrt(X)` → math.sqrt
- `mod(X, Y)` → X % Y

**Date/Time functions (`functions/datetime.py`):**

SQLite date/time model: store as TEXT (ISO-8601), REAL (Julian day), or INT (Unix timestamp).

```python
def date(timestr, *modifiers):
    """Return date in YYYY-MM-DD format."""
    t = _parse_timestring(timestr)
    for m in modifiers:
        t = _apply_modifier(t, m)
    return f"{t.year:04d}-{t.month:02d}-{t.day:02d}"

def time(timestr, *modifiers):
    """Return time in HH:MM:SS format."""
    t = _parse_timestring(timestr)
    for m in modifiers:
        t = _apply_modifier(t, m)
    return f"{t.hour:02d}:{t.minute:02d}:{t.second:02d}"

def datetime(timestr, *modifiers):
    """Return datetime in YYYY-MM-DD HH:MM:SS format."""
    t = _parse_timestring(timestr)
    for m in modifiers:
        t = _apply_modifier(t, m)
    return f"{t.year:04d}-{t.month:02d}-{t.day:02d} {t.hour:02d}:{t.minute:02d}:{t.second:02d}"

def julianday(timestr, *modifiers):
    """Return Julian day number as float."""
    from datetime import datetime, timedelta
    t = _parse_timestring(timestr)
    for m in modifiers:
        t = _apply_modifier(t, m)
    # Convert to Julian day
    a = (14 - t.month) // 12
    y = t.year + 4800 - a
    m = t.month + 12*a - 3
    jdn = t.day + (153*m + 2)//5 + 365*y + y//4 - y//100 + y//400 - 32045
    jd = jdn + (t.hour - 12) / 24.0 + t.minute / 1440.0 + t.second / 86400.0
    return jd

def strftime(fmt, timestr, *modifiers):
    """Python-style strftime (with SQLite format specifiers)."""
    t = _parse_timestring(timestr)
    for m in modifiers:
        t = _apply_modifier(t, m)
    replacements = {
        '%d': f"{t.day:02d}", '%f': f"{t.microsecond // 1000:03d}",
        '%H': f"{t.hour:02d}", '%j': str(t.timetuple().tm_yday).zfill(3),
        '%m': f"{t.month:02d}", '%M': f"{t.minute:02d}",
        '%S': f"{t.second:02d}", '%w': str(t.weekday()),
        '%W': str((t.timetuple().tm_yday + 6 - t.weekday()) // 7).zfill(2),
        '%Y': f"{t.year:04d}", '%%': '%',
    }
    result = fmt
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result

def _parse_timestring(s):
    """Parse SQLite time strings into datetime."""
    from datetime import datetime, timedelta
    # 'now' → current UTC time
    if s.upper() == 'NOW':
        return datetime.utcnow().replace(microsecond=0)
    # Julian day (float)
    try:
        jd = float(s)
        return _julian_to_datetime(jd)
    except ValueError:
        pass
    # ISO-8601 / SQLite formats
    formats = [
        '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
        '%H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S.%f',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized time string: {s}")

def _apply_modifier(t, modifier):
    """Apply SQLite time modifiers: +N days, start of month, localtime, etc."""
    from datetime import timedelta
    m = modifier.strip()
    # start of month / year / day
    if m == 'start of month':
        return t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if m == 'start of year':
        return t.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if m == 'start of day':
        return t.replace(hour=0, minute=0, second=0, microsecond=0)
    if m in ('localtime', 'utc'):
        # Simplified: skip timezone conversion for now
        return t
    # +/- N days/hours/minutes/seconds
    parts = m.split()
    if len(parts) == 3 and parts[1].isdigit():
        sign = 1 if parts[0] == '+' else -1
        amount = int(parts[1]) * sign
        unit = parts[2]
        if unit.startswith('day'):
            return t + timedelta(days=amount)
        if unit.startswith('hour'):
            return t + timedelta(hours=amount)
        if unit.startswith('minute'):
            return t + timedelta(minutes=amount)
        if unit.startswith('second'):
            return t + timedelta(seconds=amount)
        # "±NNNN months" / "±NNNN years" (approximate)
        if unit.startswith('month'):
            new_month = t.month + amount
            year_offset = (new_month - 1) // 12
            new_month = ((new_month - 1) % 12) + 1
            try:
                return t.replace(year=t.year + year_offset, month=new_month)
            except ValueError:
                return t.replace(year=t.year + year_offset, month=new_month, day=28)
        if unit.startswith('year'):
            try:
                return t.replace(year=t.year + amount)
            except ValueError:
                return t.replace(year=t.year + amount, day=28)
    raise ValueError(f"Unrecognized modifier: {m}")
```

**JSON functions (`functions/json.py`):**

Implement SQLite's JSON1 extension functions:
- `json(X)` — validate and return JSON string
- `json_array(X1, X2, ...)` — construct array
- `json_object(LABEL1, VAL1, ...)` — construct object
- `json_extract(X, P1, P2, ...)` — extract values at paths (`$`, `$.key`, `$[0]`)
- `json_set(X, P, V, ...)` — set value at path
- `json_insert(X, P, V, ...)` — insert (no overwrite)
- `json_replace(X, P, V, ...)` — replace (no insert)
- `json_remove(X, P, ...)` — remove at path
- `json_array_length(X, P?)` — length of array
- `json_type(X, P?)` — type of value at path
- `json_valid(X)` — 1 if valid JSON, 0 otherwise
- `json_quote(X)` — quote SQL value as JSON
- `json_pretty(X)` — pretty-print JSON
- `json_group_array(X)` — aggregate into array
- `json_group_object(K, V)` — aggregate into object
- `json_each(X, P?)` — table-valued function expanding array
- `json_tree(X, P?)` — table-valued function expanding full tree

Use Python's built-in `json` module for actual JSON parsing.

### 9.2 Window Functions (`functions/window.py`)

**Built-in window functions:**
- `row_number()` — sequential row number within partition
- `rank()` — rank with gaps
- `dense_rank()` — rank without gaps
- `percent_rank()` — (rank-1)/(partition_rows-1)
- `cume_dist()` — relative rank: (number of rows <= current) / partition_size
- `ntile(N)` — divide partition into N buckets
- `lag(expr, offset, default)` — value from previous row
- `lead(expr, offset, default)` — value from next row
- `first_value(expr)` — first value in window frame
- `last_value(expr)` — last value in window frame
- `nth_value(expr, N)` — Nth value in window frame

**Window function evaluation:**
1. Partition rows into groups (PARTITION BY)
2. Within each partition, sort rows (ORDER BY)
3. For each row, compute the window frame (ROWS/RANGE/GROUPS between start and end)
4. Apply the window function over the frame

**Frame computation (for aggregate window functions):**
- `ROWS BETWEEN a PRECEDING AND b FOLLOWING` — physical row offsets
- `RANGE BETWEEN a PRECEDING AND b FOLLOWING` — value range (based on ORDER BY column)
- `GROUPS BETWEEN a PRECEDING AND b FOLLOWING` — peer group offsets

### 9.3 Views (`schema.py` — view handling)

Views are stored SELECT statements. When a view is referenced in a FROM clause, the compiler substitutes the view's SELECT text into the query tree (macro expansion).

```python
class ViewDef:
    name: str
    sql: str              # original CREATE VIEW statement
    select: Select        # parsed SELECT AST
    
    def expand(self) -> Select:
        """Return the underlying SELECT, copying column aliases if needed."""
        return self.select
```

View resolution: when compiler encounters a table name in FROM that isn't a real table, it checks the view registry. If found, the view's SELECT replaces the table reference.

### 9.4 Triggers (`trigger.py`)

Triggers are stored programs that execute automatically on INSERT/UPDATE/DELETE.

```python
class TriggerDef:
    name: str
    table_name: str
    timing: str           # BEFORE, AFTER, INSTEAD OF
    event: str            # INSERT, UPDATE, DELETE
    column_list: list[str] | None  # for UPDATE OF
    when_expr: Expr | None
    statements: list[Statement]
    for_each_row: bool    # always True in SQLite
```

**Trigger Execution:**
1. When an INSERT/UPDATE/DELETE statement executes on the target table
2. Fire BEFORE triggers (in creation order)
3. Perform the actual operation
4. Fire AFTER triggers (in creation order)
5. If a trigger action modifies the same or another table, its triggers fire recursively

**Recursive trigger depth limit:** 1000 (controlled by `SQLITE_MAX_TRIGGER_DEPTH`).

**OLD and NEW references:**
- In UPDATE triggers: `OLD.column` refers to pre-update value, `NEW.column` to post-update
- In INSERT triggers: `NEW.column` only
- In DELETE triggers: `OLD.column` only
- These are resolved as special column references during trigger compilation

### 9.5 UPSERT

`INSERT ... ON CONFLICT ... DO UPDATE/NOTHING`:
```python
# Compiler resolves ON CONFLICT columns to a UNIQUE or PRIMARY KEY constraint
# On constraint violation, the DO UPDATE updates the conflicting row
# The special 'excluded' prefix refers to values that would have been inserted
```

### 9.6 RETURNING Clause

`INSERT/UPDATE/DELETE ... RETURNING expr, ...`:
```python
# After each row modification, emit the requested columns as a result row
# For UPDATE: both old.* and new.* are available
# For INSERT: new.* is available
# For DELETE: old.* is available
```

### 9.7 WITHOUT ROWID Tables

When `CREATE TABLE ... WITHOUT ROWID` is specified:
- The table uses its PRIMARY KEY as the B-Tree key
- No hidden `rowid` column exists
- All secondary indexes store PK columns instead of rowid as reference
- The B-Tree is of type INDEX (not TABLE), keyed by the PK columns

### 9.8 STRICT Tables

When `CREATE TABLE ... STRICT` is specified:
- Each column's affinity is enforced strictly
- Only INTEGER, REAL, TEXT, and BLOB are allowed as declared types
- Inserting an INT into a TEXT column raises an error (instead of auto-converting)
- The `TypeCheck` opcode validates each row before insert

### 9.9 Generated Columns

- `col TYPE GENERATED ALWAYS AS (expr) STORED` — expression stored in the row
- `col TYPE AS (expr) VIRTUAL` — expression evaluated on read
- VIRTUAL generated columns don't occupy storage space
- STORED generated columns are included in the record and updated on write

### 9.10 Full-Text Search (FTS)

**FTS5 Module (`functions/fts.py`):**

```python
class FTS5Table:
    def __init__(self, name, content_spec, tokenizer, columns):
        """
        FTS5 virtual table implementation.
        
        Storage: three shadow tables:
        - %_content: original row content (rowid, each column as text)
        - %_segdir: segment directory (level, start_block, leaves_end_block, end_block, idx)
        - %_segments: b-tree segments (blockid, block)
        - %_docsize: document size per column (docid, sz)
        - %_idx: index mapping
        """
    
    def match(self, query: str) -> list[int]:
        """FTS5 match query syntax:
        - term          → basic term (case-insensitive)
        - "phrase"      → exact phrase
        - term1 AND term2 → intersection
        - term1 OR term2  → union
        - term1 NOT term2 → difference
        - term1 NEAR/n term2 → proximity
        - prefix*       → prefix search
        - ^term         → term must be first in column
        - column:query  → search specific column
        """
    
    def bm25_score(self, docid: int, query: str) -> float:
        """BM25 ranking algorithm for relevance scoring."""
```

**Tokenizers:**
- `unicode61`: Unicode text tokenization (default)
- `ascii`: ASCII only tokenization
- `porter`: Porter stemming
- `trigram`: N-gram tokenization (3-character tokens)

### 9.11 PRAGMA Commands

Every pragma is implemented as a method on the Database class. Parser handles PRAGMA statements and dispatches to the appropriate handler.

```python
class PragmaHandler:
    """Base class for all pragma implementations."""
    
    def __init__(self, db):
        self.db = db
    
    def handle_query(self) -> list[tuple]:
        """PRAGMA name — return current value."""
        raise NotImplementedError
    
    def handle_set(self, value):
        """PRAGMA name = value — set and return new value."""
        raise NotImplementedError
```

**Pragma categories:**

**Query only (read metadata):**
- `table_info(table)` — column metadata for table
- `table_xinfo(table)` — includes hidden columns (rowid, etc.)
- `index_info(index)` — columns in an index
- `index_list(table)` — all indexes on a table
- `foreign_key_list(table)` — FK constraints
- `database_list` — attached databases
- `function_list` — registered functions
- `module_list` — registered virtual table modules
- `pragma_list` — all pragmas
- `compile_options` — build options
- `stats` — B-Tree page counts per table

**State get/set:**
- `schema_version`, `user_version`, `application_id`
- `page_count`, `freelist_count`, `max_page_count`
- `page_size`, `cache_size`, `cache_spill`, `mmap_size`
- `journal_mode`, `journal_size_limit`, `synchronous`
- `auto_vacuum`, `incremental_vacuum`
- `locking_mode`, `busy_timeout`
- `temp_store`, `trusted_schema`
- `foreign_keys`, `defer_foreign_keys`, `recursive_triggers`
- `encoding`, `strict`, `legacy_alter_table`
- `reverse_unordered_selects`, `query_only`, `read_uncommitted`, `writable_schema`

**Maintenance:**
- `integrity_check` — full database integrity verification
- `quick_check` — faster integrity check (skip some checks)
- `optimize` — optimize database (analyze, vacuum if beneficial)
- `wal_checkpoint` — checkpoint WAL to database

### 9.12 Integrity Check Algorithm

```python
def integrity_check(self) -> list[str]:
    errors = []
    # 1. Verify header page
    errors += self._check_header()
    # 2. Verify page allocation: every page is either in a B-Tree or on freelist
    errors += self._check_page_allocation()
    # 3. For each B-Tree, verify structure
    for table in self.schema.tables.values():
        if table.root_page > 0:
            errors += self._check_btree(table.root_page, table.name, is_table=True)
    for index in self.schema.indexes.values():
        if index.root_page > 0:
            errors += self._check_btree(index.root_page, index.name, is_table=False)
    # 4. Verify index entries match table rows
    errors += self._check_indexes_match_tables()
    # 5. Verify foreign key constraints
    if self.transaction_manager.fk_constraints_enabled:
        errors += self._check_foreign_keys()
    # 6. Verify sqlite_schema contents
    errors += self._check_schema_table()
    return errors or ['ok']
```

## 10. Phase 8: CLI & Ecosystem

### 10.1 Command-Line REPL (`cli.py`)

```python
class CLI:
    def __init__(self):
        self.db = None
        self.history_file = os.path.expanduser('~/.pysqlite_history')
        self.mode = 'list'        # list, column, csv, json, markdown, box, insert
        self.headers = True
        self.separator = '|'
        self.null_value = ''
        self.timer = False
        self.echo = False
        self.prompt = 'pysqlite> '
        self.continue_prompt = '   ...> '
    
    def run(self):
        """Main REPL loop."""
        import readline
        readline.read_history_file(self.history_file)
        
        while True:
            try:
                line = input(self.prompt)
                if line.startswith('.'):
                    self._handle_dot_command(line[1:])
                else:
                    self._execute_sql(line)
            except (KeyboardInterrupt, EOFError):
                print()
                break
            except DatabaseError as e:
                print(f"Error: {e}")
        
        readline.write_history_file(self.history_file)
    
    def _execute_sql(self, sql: str):
        """Execute SQL and display results."""
        start = time.time()
        cursor = self.db.execute(sql)
        elapsed = time.time() - start
        
        if cursor.description:
            self._display_results(cursor)
        
        if self.timer:
            print(f"Time: {elapsed:.3f}s")
        if self.echo:
            print(f"Rows affected: {cursor.rowcount}")
    
    def _display_results(self, cursor):
        """Format and display query results based on current mode."""
        if self.mode == 'list':
            self._display_list(cursor)
        elif self.mode == 'column':
            self._display_column(cursor)
        elif self.mode == 'csv':
            self._display_csv(cursor)
        elif self.mode == 'json':
            self._display_json(cursor)
        elif self.mode == 'markdown':
            self._display_markdown(cursor)
        elif self.mode == 'box':
            self._display_box(cursor)
        elif self.mode == 'insert':
            self._display_insert(cursor)
```

**Dot commands (full list):**
- `.open [FILE]` — open database
- `.tables [PATTERN]` — list tables
- `.schema [TABLE]` — show CREATE statements
- `.indexes [TABLE]` — list indexes
- `.dump [TABLE]` — dump as SQL
- `.import FILE TABLE` — import CSV
- `.output [FILE]` — redirect output to file
- `.mode MODE` — set output mode
- `.headers ON|OFF` — toggle headers
- `.separator STR` — set field separator
- `.nullvalue STR` — set NULL display
- `.timer ON|OFF` — toggle query timer
- `.echo ON|OFF` — toggle SQL echo
- `.databases` — list attached databases
- `.dbinfo` — database metadata
- `.exit` / `.quit` — exit
- `.help` — help message
- `.backup FILE` — backup database
- `.restore FILE` — restore from backup
- `.save FILE` — save in-memory db to file
- `.clone FILE` — clone database
- `.read FILE` — execute SQL from file
- `.prompt MAIN CONTINUE` — set prompts
- `.show` — show current settings
- `.stats` — show memory/disk stats

### 10.2 Python DB-API 2.0 Module (`__init__.py`)

```python
class Connection:
    """SQLite database connection."""
    
    def __init__(self, database: str, timeout=5.0, isolation_level='',
                 check_same_thread=True, cached_statements=100, uri=False):
        self.database = database
        self.timeout = timeout
        self.isolation_level = isolation_level
        self.row_factory = None
        self.text_factory = str
        self.total_changes = 0
        self._db = Database(database)
        self._cached_programs: dict[str, list[Instruction]] = {}
    
    def cursor(self, factory=None) -> 'Cursor':
        """Create a new cursor."""
        factory = factory or Cursor
        return factory(self)
    
    def execute(self, sql: str, parameters=()) -> 'Cursor':
        """Shortcut: execute and return cursor."""
        c = self.cursor()
        c.execute(sql, parameters)
        return c
    
    def executemany(self, sql: str, parameters) -> 'Cursor':
        c = self.cursor()
        c.executemany(sql, parameters)
        return c
    
    def executescript(self, sql: str) -> 'Cursor':
        c = self.cursor()
        c.executescript(sql)
        return c
    
    def commit(self):
        """Commit current transaction."""
        self._db.commit()
    
    def rollback(self):
        """Rollback current transaction."""
        self._db.rollback()
    
    def close(self):
        """Close connection."""
        self._db.close()
    
    def create_function(self, name, narg, func, deterministic=False):
        """Register a custom scalar function."""
        self._db.create_function(name, narg, func)
    
    def create_aggregate(self, name, narg, aggregate_class):
        """Register a custom aggregate function."""
        self._db.create_aggregate(name, narg, aggregate_class)
    
    def create_collation(self, name, callable):
        """Register a custom collation."""
        self._db.create_collation(name, callable)
    
    def set_authorizer(self, authorizer_callback):
        """Set table/column access authorizer."""
        self._db.authorizer = authorizer_callback
    
    def set_progress_handler(self, handler, n):
        """Set progress callback (called every n VM operations)."""
        self._db.progress_handler = handler
        self._db.progress_interval = n
    
    def set_trace_callback(self, trace):
        """Set SQL trace callback."""
        self._db.trace_callback = trace
    
    def enable_load_extension(self, enabled):
        """Enable extension loading (no-op — extensions not supported in pure Python)."""
        pass
    
    def load_extension(self, path):
        pass
    
    def backup(self, target, *, pages=-1, name='main', sleep=0.25):
        """Backup database to another connection."""
        # Copy pages one by one
        self._db.backup(target._db, pages, name, sleep)
    
    def iterdump(self):
        """Iterate SQL statements to dump database."""
        for table in self._db.schema.tables.values():
            yield table.sql + ';'
            # INSERT statements for each row
            cursor = self.execute(f"SELECT * FROM \"{table.name}\"")
            for row in cursor.fetchall():
                cols = ', '.join(f'"{c}"' for c in table.columns)
                vals = ', '.join(self._quote_value(v) for v in row)
                yield f"INSERT INTO \"{table.name}\" ({cols}) VALUES ({vals});"
            yield ''
        for view in self._db.schema.views.values():
            yield view.sql + ';'

class Cursor:
    """Database cursor."""
    
    def __init__(self, connection: Connection):
        self.connection = connection
        self.description = None
        self.rowcount = -1
        self.arraysize = 1
        self.lastrowid = None
        self._results: list[list] = []
        self._index = 0
    
    def execute(self, sql: str, parameters=()):
        """Execute a single SQL statement."""
        # Parameter substitution
        if parameters:
            sql = self._substitute_parameters(sql, parameters)
        if self.connection._db.trace_callback:
            self.connection._db.trace_callback(sql)
        self._results = self.connection._db.execute(sql)
        self.description = self._build_description()
        self.lastrowid = self.connection._db.last_rowid
        self.rowcount = len(self._results)
        self._index = 0
        return self
    
    def executemany(self, sql: str, parameters):
        """Execute SQL with each parameter set."""
        self._results = []
        for params in parameters:
            self.execute(sql, params)
            self._results.extend(self._results)
        return self
    
    def executescript(self, sql: str):
        """Execute multiple SQL statements separated by ';'."""
        self.connection._db.executescript(sql)
        return self
    
    def fetchone(self):
        """Fetch next row."""
        if self._index >= len(self._results):
            return None
        row = self._results[self._index]
        self._index += 1
        if self.connection.row_factory:
            row = self.connection.row_factory(self, row)
        return row
    
    def fetchmany(self, size=None):
        """Fetch next size rows."""
        if size is None:
            size = self.arraysize
        rows = self._results[self._index:self._index + size]
        self._index += len(rows)
        return rows
    
    def fetchall(self):
        """Fetch all remaining rows."""
        rows = self._results[self._index:]
        self._index = len(self._results)
        return rows
    
    def close(self):
        self._results = None
    
    def __iter__(self):
        return self
    
    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row
    
    def _substitute_parameters(self, sql: str, parameters) -> str:
        """Replace ? / :name / $name / @name placeholders with values."""
        # qmark style: ?
        # named style: :name, @name, $name
        # numeric: ?1, ?2, etc.
        if isinstance(parameters, dict):
            for key, val in parameters.items():
                sql = sql.replace(f':{key}', self._quote_value(val))
                sql = sql.replace(f'@{key}', self._quote_value(val))
                sql = sql.replace(f'${key}', self._quote_value(val))
        else:
            params = list(parameters)
            # ? placeholders (positional)
            i = 0
            result = []
            for part in sql.split('?'):
                if i == 0:
                    result.append(part)
                else:
                    result.append(self._quote_value(params[i - 1]))
                    result.append(part)
                i += 1
            # ?NNN placeholders
            import re
            sql = re.sub(r'\?(\d+)', lambda m: self._quote_value(params[int(m.group(1)) - 1]), ''.join(result))
        return sql
    
    def _quote_value(self, val) -> str:
        """Quote a Python value for SQL insertion."""
        if val is None:
            return 'NULL'
        if isinstance(val, bool):
            return '1' if val else '0'
        if isinstance(val, int):
            return str(val)
        if isinstance(val, float):
            return repr(val)
        if isinstance(val, str):
            return "'" + val.replace("'", "''") + "'"
        if isinstance(val, (bytes, bytearray)):
            return "x'" + val.hex() + "'"
        return "'" + str(val).replace("'", "''") + "'"
    
    def _build_description(self):
        """Build cursor.description from result metadata."""
        if not self._results:
            return None
        return [
            (f"col{i}", None, None, None, None, None, None)
            for i in range(len(self._results[0]))
        ]
```

## 11. Phase 9: Testing & Validation

### 11.1 Test Categories

| Category | Directory | Description |
|----------|-----------|-------------|
| Unit tests | tests/unit/ | Test each module in isolation with mocked dependencies |
| SQL integration | tests/sql/ | Test SQL queries end-to-end |
| Compatibility | tests/compat/ | Cross-validate with real SQLite |
| Stress | tests/stress/ | Large data volumes, long transactions |
| Fuzz | tests/fuzz/ | Random SQL generation, corrupted database files |
| Regression | tests/regression/ | Bug reproduction cases |

### 11.2 Unit Test Coverage

**test_vfs.py:** File creation, read/write, sync, truncate, locking, memory VFS, error handling
**test_pager.py:** Page read/write, cache eviction, journal creation/commit/rollback, hot journal recovery, freelist management, page allocation/free
**test_btree.py:** Page structure, cell insertion/deletion, page split/merge, cursor navigation (first, last, next, prev, seek), overflow pages
**test_record.py:** Serial type encoding/decoding, all integer sizes, float, text, blob, NULL, 0, 1 special cases
**test_lexer.py:** All token types, operators, string escapes, comments, keywords case-insensitivity, error handling
**test_parser.py:** All SQL constructs parse to correct AST, expression precedence, error recovery
**test_compile.py:** Program emission for each statement type, register allocation, label resolution
**test_vm.py:** Each opcode behavior, comparison semantics, type affinity, aggregation, transaction opcodes

### 11.3 SQL Integration Tests

Each test follows the pattern:
```python
def test_simple_select():
    db = Database(":memory:")
    db.execute("CREATE TABLE t (a INT, b TEXT)")
    db.execute("INSERT INTO t VALUES (1, 'hello')")
    db.execute("INSERT INTO t VALUES (2, 'world')")
    results = db.execute("SELECT * FROM t WHERE a = 1")
    assert results == [(1, 'hello')]
```

**DDL tests:** Create table with all column types, constraints, WITHOUT ROWID, STRICT, generated columns, temp tables, IF NOT EXISTS
**DML tests:** Simple INSERT, INSERT from SELECT, multi-row INSERT, UPDATE with SET/WHERE/ORDER BY/LIMIT, DELETE with WHERE/ORDER BY/LIMIT
**SELECT tests:** DISTINCT, WHERE with all operators, ORDER BY (ASC/DESC/NULLS FIRST/LAST), GROUP BY with aggregates, HAVING, LIMIT/OFFSET, compound SELECT (UNION/INTERSECT/EXCEPT)
**Expression tests:** Arithmetic, string concatenation, LIKE/GLOB/MATCH/REGEXP, IN/NOT IN, BETWEEN, CASE, CAST, subqueries (scalar/EXISTS/IN), COLLATE
**JOIN tests:** INNER/LEFT/RIGHT/FULL/CROSS/NATURAL, ON vs USING, self-joins, multi-table joins, subqueries in FROM
**Index tests:** CREATE INDEX, UNIQUE index enforcement, partial indexes, functional indexes, index usage in WHERE, INDEXED BY/NOT INDEXED, REINDEX
**Transaction tests:** BEGIN/COMMIT/ROLLBACK, savepoints, nested transactions, rollback to savepoint, concurrent access locking
**Constraint tests:** NOT NULL, UNIQUE, PRIMARY KEY, CHECK, FOREIGN KEY (CASCADE/SET NULL/SET DEFAULT/RESTRICT), AUTOINCREMENT
**Trigger tests:** BEFORE/AFTER/INSTEAD OF, INSERT/UPDATE/DELETE events, OLD/NEW references, WHEN clause, recursive triggers
**View tests:** CREATE/DROP VIEW, query expansion, column aliases, ALTER TABLE RENAME affecting views
**Alter tests:** RENAME TO, RENAME COLUMN, ADD COLUMN, DROP COLUMN
**UPSERT tests:** ON CONFLICT DO NOTHING, ON CONFLICT DO UPDATE with EXCLUDED
**RETURNING tests:** INSERT/UPDATE/DELETE RETURNING *
**Generated column tests:** VIRTUAL vs STORED, constraints on generated columns
**JSON tests:** All JSON creation, extraction, modification, aggregate functions
**FTS tests:** Create FTS5 table, MATCH queries, bm25 ranking, prefix/phrase/NEAR queries
**Window tests:** ROW_NUMBER, RANK, DENSE_RANK, NTILE, LAG/LEAD, frame specifications (ROWS/RANGE/GROUPS), window aggregation
**PRAGMA tests:** Every pragma query and set variant, error handling for invalid values

### 11.4 Compatibility Tests

Use the real sqlite3 command-line tool to create reference databases and compare results:
```python
import subprocess
import tempfile

def test_compat_create_and_read():
    ref_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    subprocess.run(['sqlite3', ref_db.name, """
        CREATE TABLE t (a INT, b TEXT);
        INSERT INTO t VALUES (1, 'hello');
        INSERT INTO t VALUES (2, 'world');
    """], check=True)
    
    our_db = Database(ref_db.name)
    results = our_db.execute("SELECT * FROM t ORDER BY a")
    assert results == [(1, 'hello'), (2, 'world')]
    
    our_db.execute("INSERT INTO t VALUES (3, '!!!')")
    our_db.close()
    
    result = subprocess.run(['sqlite3', ref_db.name,
        'SELECT count(*) FROM t'], capture_output=True, text=True)
    assert result.stdout.strip() == '3'
```

### 11.5 Stress Tests

```python
def test_large_insert():
    db = Database(":memory:")
    db.execute("CREATE TABLE t (a INT, b TEXT, c REAL)")
    n = 100000
    for i in range(n):
        db.execute("INSERT INTO t VALUES (?, ?, ?)", (i, f"row{i}", float(i)))
    results = db.execute("SELECT count(*) FROM t")
    assert results[0][0] == n
```

### 11.6 Fuzz Testing

```python
import random
import string

def _random_sql():
    tables = ['t1', 't2']
    cols = ['a', 'b', 'c']
    ops = ['=', '<', '>', '<=', '>=', '<>', 'LIKE', 'IN', 'BETWEEN']
    return random.choice([
        f"SELECT {random.choice(cols)} FROM {random.choice(tables)} WHERE {random.choice(cols)} {random.choice(ops)} {random.randint(1, 100)}",
        f"INSERT INTO {random.choice(tables)} VALUES ({random.randint(1, 100)}, '{_random_string()}')",
        f"UPDATE {random.choice(tables)} SET {random.choice(cols)} = {random.randint(1, 100)} WHERE {random.choice(cols)} {random.choice(ops)} {random.randint(1, 100)}",
        f"DELETE FROM {random.choice(tables)} WHERE {random.choice(cols)} IS NULL",
    ])

def _random_string():
    return ''.join(random.choices(string.ascii_letters, k=random.randint(0, 20)))

def test_fuzz_random_sql():
    db = Database(":memory:")
    db.execute("CREATE TABLE t1 (a INT, b TEXT, c REAL)")
    db.execute("CREATE TABLE t2 (x INT, y TEXT)")
    for i in range(100):
        db.execute("INSERT INTO t1 VALUES (?, ?, ?)", (i, f"v{i}", float(i)))
    for _ in range(1000):
        sql = _random_sql()
        try:
            db.execute(sql)
        except DatabaseError:
            pass
```

## 12. Phase 10: Performance Tuning

### 12.1 Python-Level Optimizations

1. Use __slots__ on all hot-path classes: Register, Page, Cell, Cursor, Instruction, AST nodes
2. Pre-allocate register list: Use a fixed-size list of Register objects instead of a dict keyed by int
3. Inline hot functions: varint_decode, varint_encode should be inlined in the VM loop
4. Cache record column offsets: Pre-compute column offsets when decoding records, store in cursor
5. Use local variable bindings in the VM dispatch loop
6. Avoid method calls in hot loops; use dict dispatch table

### 12.2 B-Tree Optimizations

1. Page cache with LRU eviction using collections.OrderedDict
2. Bulk insert optimization: gather, sort by key, write sequentially
3. Cursor reuse across multiple operations
4. Page pre-fetching during sequential scans

### 12.3 Query Compiler Optimizations

1. Constant folding: evaluate 1+2 at compile time
2. Predicate pushdown: move WHERE closer to scan
3. COUNT(*) optimization using B-Tree page count metadata
4. MAX/MIN on indexed column: direct index lookup
5. IN list optimization: sort + binary search
6. Join order: most selective table first

### 12.4 Pager Optimizations

1. Batch page writes: collect dirty pages, write together
2. mmap I/O for reads to avoid copy overhead
3. Zero-copy page reads via memoryview
4. WAL mode for better concurrency
5. Larger default cache (1MB instead of 2KB)

## 13. Implementation Milestones

### Milestone 1: VFS + Pager (Days 1-3)
- Files: vfs.py, pager.py
- Create a .db file, valid header, page read/write, ACID journal
- Test: pytest tests/unit/test_vfs_pager.py

### Milestone 2: B-Tree + Records (Days 4-7)
- Files: cell.py, record.py, btree.py
- Insert/read/delete via B-Tree cursor, page splitting, overflow pages
- Test: pytest tests/unit/test_btree.py

### Milestone 3: SQL Lexer + Parser (Days 8-12)
- Files: lexer.py, parser.py, ast.py
- Parse all major SQL constructs into AST
- Test: pytest tests/unit/test_lexer.py tests/unit/test_parser.py

### Milestone 4: Minimal VDBE (Days 13-20)
- Files: opcode.py, compile.py, vm.py
- CREATE TABLE, INSERT, SELECT * working end-to-end
- Test: pytest tests/sql/test_basic.py

### Milestone 5: WHERE + Expressions + ORDER BY (Days 21-25)
- Filtered queries, comparison operators, sorting
- Test: pytest tests/sql/test_expressions.py

### Milestone 6: Indexes (Days 26-30)
- CREATE INDEX, automatic index usage, UNIQUE enforcement
- Test: pytest tests/sql/test_indexes.py

### Milestone 7: JOINs (Days 31-35)
- All join types, auto-indexes for join columns
- Test: pytest tests/sql/test_joins.py

### Milestone 8: GROUP BY + Aggregates (Days 36-40)
- GROUP BY with all aggregate functions, HAVING
- Test: pytest tests/sql/test_aggregates.py

### Milestone 9: Subqueries + CTEs (Days 41-46)
- Scalar/EXISTS/IN/correlated subqueries, recursive CTEs
- Test: pytest tests/sql/test_subqueries.py

### Milestone 10: Window Functions (Days 47-52)
- All window functions, ROWS/RANGE/GROUPS frames
- Test: pytest tests/sql/test_window.py

### Milestone 11: Transactions + Savepoints (Days 53-56)
- BEGIN/COMMIT/ROLLBACK, nested savepoints, ACID
- Test: pytest tests/sql/test_transactions.py

### Milestone 12: Constraints (Days 57-62)
- PK, UNIQUE, FK, CHECK, NOT NULL, AUTOINCREMENT
- Test: pytest tests/sql/test_fk.py

### Milestone 13: UPDATE + DELETE + UPSERT + RETURNING (Days 63-68)
- Complex WHERE, ON CONFLICT, RETURNING clause
- Test: pytest tests/sql/test_update_delete.py

### Milestone 14: Triggers + Views (Days 69-74)
- All trigger types, view expansion, recursive triggers
- Test: pytest tests/sql/test_triggers.py

### Milestone 15: ALTER TABLE (Days 75-78)
- RENAME TO/COLUMN, ADD/DROP COLUMN
- Test: pytest tests/sql/test_alter.py

### Milestone 16: Full Function Set (Days 79-85)
- All 80+ scalar, date/time, JSON, math functions
- Test: pytest tests/sql/test_json.py

### Milestone 17: PRAGMAs (Days 86-89)
- Every PRAGMA, query and set variants
- Test: pytest tests/sql/test_pragmas.py

### Milestone 18: CLI (Days 90-94)
- Full REPL, dot commands, all output modes
- Manual testing

### Milestone 19: Python DB-API (Days 95-98)
- pysqlite.connect(), Cursor with parameter binding
- Test: pytest tests/sql/test_dbapi.py

### Milestone 20: FTS + WITHOUT ROWID + STRICT (Days 99-105)
- FTS5 implementation, clustered tables, strict typing
- Test: pytest tests/sql/test_fts.py

### Milestone 21: Integrity + Analyze + Compatibility (Days 106-112)
- PRAGMA integrity_check, ANALYZE, cross-validation
- Test: pytest tests/compat/

### Milestone 22: Performance + Polish (Days 113-120)
- Profiling, optimization, WAL mode, fuzz testing
- Test: pytest tests/fuzz/

---

## Appendix A: Database File Format Reference

### Page 1 -- Database Header (bytes 0-99)

Offset  Size  Description
0       16    Header string: "SQLite format 3\0"
16       2    Page size in bytes (512..65536, power of 2)
18       1    File format write version
19       1    File format read version
20       1    Bytes of reserved space
21       1    Max embedded payload fraction (64)
22       1    Min embedded payload fraction (32)
23       1    Leaf payload fraction (32)
24       4    File change counter
28       4    Size of database in pages
32       4    First freelist trunk page
36       4    Total freelist pages
40       4    Schema cookie
44       4    Schema format number
48       4    Default page cache size
52       4    Largest root B-Tree page
56       4    Text encoding (1=UTF-8)
60       4    User version
64       4    Incremental vacuum mode
68       4    Application ID
72      20    Reserved
92       4    Version-valid-for
96       4    SQLite version number

### Page Layout

Offset  Size  Description
0       1     Page type flag
1       2     First freeblock offset
3       2     Number of cells
5       2     Cell content offset
7       1     Fragmented free bytes
8       4     Rightmost child page (interior only)
12      N     Cell pointer array (2 bytes per cell)

### Page Type Flags

0x02  Interior index page
0x05  Interior table page
0x0A  Leaf index page
0x0D  Leaf table page

### Cell Formats

Table Leaf Cell: [varint: payload_len][varint: rowid][payload]
Table Interior Cell: [varint: left_child][varint: key]
Index Leaf Cell: [varint: payload_len][payload]
Index Interior Cell: [varint: left_child][varint: payload_len][payload]

### Record Format

[varint: header_size][varint: serial_type_1]...[serial_type_N][data_1]...[data_N]

---

## Appendix B: Varint Encoding Reference

| Value Range | Bytes | Description |
|-------------|-------|-------------|
| 0-240 | 1 | Single byte |
| 241-2287 | 2 | Two-byte |
| 2288-67823 | 3 | Three-byte |
| >67823 | 3-9 | Standard 7-bit/byte with continuation bit |
| 9th byte | 9 | All 8 bits are data |

## Appendix C: Serial Type Reference

| Code | Type | Bytes |
|------|------|-------|
| 0 | NULL | 0 |
| 1 | INT8 | 1 |
| 2 | INT16 | 2 |
| 3 | INT24 | 3 |
| 4 | INT32 | 4 |
| 5 | INT48 | 6 |
| 6 | INT64 | 8 |
| 7 | FLOAT64 | 8 |
| 8 | INTEGER 0 | 0 |
| 9 | INTEGER 1 | 0 |
| 10-11 | Reserved | -- |
| >=12 even | BLOB (N-12)/2 | (N-12)/2 |
| >=13 odd | TEXT (N-13)/2 | (N-13)/2 |

## Appendix D: Lock Protocol

UNLOCKED -> SHARED: BEGIN DEFERRED or first SELECT
UNLOCKED -> RESERVED: BEGIN IMMEDIATE
UNLOCKED -> EXCLUSIVE: BEGIN EXCLUSIVE
SHARED -> SHARED: Additional readers allowed
SHARED -> RESERVED: First write operation
RESERVED -> PENDING: Before commit, wait for readers
PENDING -> EXCLUSIVE: All readers finished
EXCLUSIVE -> SHARED: After commit (if still reading)
EXCLUSIVE -> UNLOCKED: After commit (if no more reads)
