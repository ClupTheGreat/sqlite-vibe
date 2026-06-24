# Detected Problems

> Use this file to log bugs, design issues, edge cases, and TODO items found during implementation.
> Format: `[Date] Description (file:line, severity: high/med/low)`

---

## How to Log Problems

When you encounter a problem during development, add an entry like:

```
[2026-06-24] Brief description of the issue
  - File: pysqlite/vm.py:142
  - Severity: high | medium | low
  - Details: extended explanation, root cause if known, suggested fix
```

## Log

```
[2026-06-24] OSVFS Windows locking hangs (LockFileEx)
  - File: pysqlite/vfs.py:108-130
  - Severity: medium
  - Details: LockFileEx with OVERLAPPED hangs on Python 3.13/Windows.
    ctypes.wintypes.OVERLAPPED missing; custom OVERLAPPED struct defined
    but LockFileEx still blocks. OSVFS lock tests (shared/exclusive/reserved)
    are marked skip. Need to investigate correct OVERLAPPED setup or use
    alternative locking via msvcrt.locking().

[2026-06-24] Pager commit doesn't sync journal count before file change counter
  - File: pysqlite/pager.py:334-335
  - Severity: low
  - Details: In commit_transaction, file_change_counter increment and write
    happen after journal is finalized. On crash between write and journal
    sync, counter increment could be lost. Not critical for current tests.

[2026-06-24] MemoryVFS write/read handles past-end inconsistently
  - File: pysqlite/vfs.py:134-154, 323-329
  - Severity: low
  - Details: OSVFS.read pads partial reads with zeros; MemoryVFS.read now
    does same. But OSVFS.write doesn't extend file - relies on OS semantics.
    MemoryVFS.write extends buffer. This asymmetry is fine for now.

[2026-06-24] _find_cell_end returned same offset as cell start for last cell
  - File: pysqlite/btree.py:71-79 (fixed)
  - Severity: high
  - Details: _find_cell_end returned cell_content_offset for the last cell,
    but after _allocate_space decremented it to equal the cell's start offset,
    read_cell returned empty bytes. Fixed by scanning all cell pointers for
    the next higher offset (or page_size).

[2026-06-24] _defragment packed cells downward from cell_content_offset (wrong direction)
  - File: pysqlite/btree.py:170-189 (fixed)
  - Severity: high
  - Details: Defrag packed cells starting from cell_content_offset going downward
    toward zero, causing negative offsets on full pages. Fixed to pack from
    page_size (bottom of page) upward.

[2026-06-24] _pointer_offset used base 8 for all page types, corrupting interior page headers
  - File: pysqlite/btree.py:111 (fixed)
  - Severity: high
  - Details: _pointer_offset used base offset 8 for all page types, but interior
    pages have a 12-byte header (8 common + 4 for right_child). Cell pointer
    at offset 8 overwrote first 2 bytes of right_child. Fixed to use
    header_size (12 for interior, 8 for leaf).

[2026-06-24] _balance created new root with swapped left/right children
  - File: pysqlite/btree.py:587-601 (fixed)
  - Severity: high
  - Details: When creating a new root during leaf split, the old page (smaller
    keys) was assigned as right_child and the new page (larger keys) as
    left_child of the promoted cell. Fixed to match B-tree semantics.

[2026-06-24] BTreeCursor methods used stale cached root_page instead of btree.root_page
  - File: pysqlite/btree.py:insert/first/last/seek (fixed)
  - Severity: high
  - Details: insert, first, last, and seek used self.root_page (captured at
    cursor creation) instead of self.btree.root_page (which updates after
    root splits). All fixes inserted remained on the original leaf page
    even after the root was replaced. Fixed all to use self.btree.root_page.

[2026-06-24] next() re-entered same child page instead of advancing to next sibling
  - File: pysqlite/btree.py:285-299 (fixed)
  - Severity: high
  - Details: After exhausting a leaf page, next() popped the parent stack
    entry and re-entered the same cell's left_child (the page just finished)
    instead of advancing to the next cell's left_child or right_child.
    Fixed to increment parent_idx appropriately.

[2026-06-24] insert_cell raised CorruptError on page full instead of allowing caller to split
  - File: pysqlite/btree.py:115-134 (fixed)
  - Severity: high
  - Details: insert_cell's _allocate_space raised CorruptError("Page full")
    when the page ran out of space, preventing the cursor's post-insert split
    check from ever running. Fixed _allocate_space to return -1 and
    insert_cell to return False on failure. Cursor.insert now pre-splits
    by calling _balance with extra_cell when insert_cell fails.

[2026-06-24] _balance did not include new cell in split entries
  - File: pysqlite/btree.py:648-677 (fixed)
  - Severity: high
  - Details: When the page was full and insert_cell returned False, _balance
    only split the existing cells (excluding the pending new cell). After
    the split, the recursive retry would try to insert the large cell into
    one of the split halves, which was also full, causing infinite splits.
    Fixed by adding an extra_cell parameter to _balance that includes the
    pending cell in the split distribution.

[2026-06-24] first() and last() did not clear cursor stack
  - File: pysqlite/btree.py:303, 330 (fixed)
  - Severity: medium
  - Details: first() and last() appended to the cursor's stack without
    clearing it first, causing stale entries from prior operations to
    accumulate. This caused current_key() to return wrong results after
    delete+first. Fixed by adding self.stack = [] at the start.

[2026-06-24] delete() did not flush page modifications to pager
  - File: pysqlite/btree.py:727-742 (fixed)
  - Severity: high
  - Details: delete_cell modified the BTreePage's raw_data buffer but
    delete() never called page.flush(), so the pager's cache held stale
    data. Subsequent first() from a fresh BTreePage read the old data.
    Fixed by adding page.flush() after delete_cell.

[2026-06-24] _rebalance_after_delete left root as interior with 0 cells
  - File: pysqlite/btree.py:744-795 (fixed)
  - Severity: medium
  - Details: After cascading page frees up to the root, if the root had
    0 cells (interior) and right_child was set to 0, first() would try
    to read page 0 (invalid). Fixed by converting the root to a leaf
    page if it's interior with 0 cells after rebalance.
```


