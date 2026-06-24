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

[2026-06-24] Lexer _read_operator matched 2-char ops before 3-char (-> before ->>)
  - File: pysqlite/lexer.py:362-374 (fixed)
  - Severity: high
  - Details: _read_operator checked 2-character operators first. For "->>", it
    matched "->" (ARROW) and left ">" as a separate GT token. Fixed to check
    3-character operators ("->>") first before falling back to 2-char.

[2026-06-24] Lexer _emit used self.col after advance (wrong start column)
  - File: pysqlite/lexer.py:259-263 (fixed)
  - Severity: medium
  - Details: _emit defaulted to self.col which had already advanced past the
    token. Fixed by storing start line/col per-token and using those in _emit.

[2026-06-24] Parser CREATE TABLE/VIEW didn't consume TABLE/VIEW keyword before name
  - File: pysqlite/parser.py:154, 400 (fixed)
  - Severity: high
  - Details: _parse_create_table and _parse_create_view didn't advance past
    TABLE/VIEW before calling _parse_table_name(), causing "Expected IDENTIFIER,
    got TABLE/VIEW" errors. Added self.advance() before IF NOT EXISTS check.

[2026-06-24] Parser CREATE didn't handle UNIQUE before INDEX
  - File: pysqlite/parser.py:144 (fixed)
  - Severity: high
  - Details: _parse_create checked tt == INDEX but not tt == UNIQUE, so
    "CREATE UNIQUE INDEX" failed. Added UNIQUE to the dispatch condition.

[2026-06-24] Parser DROP consumed IF EXISTS before dispatching to sub-methods
  - File: pysqlite/parser.py:468-515 (fixed)
  - Severity: high
  - Details: _parse_drop set tt before consuming IF EXISTS, then dispatched
    by tt. Sub-methods then saw IF as the next token instead of the name.
    Fixed by moving IF EXISTS consumption into each sub-method.

[2026-06-24] Parser ROLLBACK dispatch checked wrong token type
  - File: pysqlite/parser.py:58 (fixed)
  - Severity: medium
  - Details: _parse_statement checked TokenType.ROLLBACK_STMT but the lexer
    emits TokenType.ROLLBACK. Changed to TokenType.ROLLBACK.

[2026-06-24] Parser NOT NULL used non-existent TokenType.NOTNULL
  - File: pysqlite/parser.py:1008-1019 (fixed)
  - Severity: high
  - Details: Parser checked TokenType.NOTNULL which didn't exist in the enum.
    Fixed by advancing on NOT then checking for NULL with two-token lookahead.

[2026-06-24] Parser join table_ref wrapped JoinClause in tuple
  - File: pysqlite/parser.py:652-653 (fixed)
  - Severity: high
  - Details: _parse_table_ref returned (JoinClause(...),) instead of
    JoinClause(...), causing isinstance checks in tests to fail. Fixed by
    returning jc directly.

[2026-06-24] TokenType enum missing several keywords used by parser
  - File: pysqlite/lexer.py:8-57 (fixed)
  - Severity: high
  - Details: TokenType was missing NULLS, ADD, COLUMN, TRANSACTION, RENAME,
    BEFORE, AFTER, INSTEAD, FIRST, LAST. All added with keyword mappings.

[2026-06-24] Compiler _compile_binary_op used P2 as jump address for arithmetic ops
  - File: pysqlite/compile.py:370-385 (fixed)
  - Severity: high
  - Details: Binary operator compilation for arithmetic (Add, Subtract, etc.)
    set P2 to an instruction index (for label patching) instead of the
    destination register. Split arithmetic and comparison maps; arithmetic
    ops use P2=dest, comparison ops use P2=jump with proper label patching.

[2026-06-24] _rebalance_after_delete left root as interior with 0 cells
  - File: pysqlite/btree.py:744-795 (fixed)
  - Severity: medium
  - Details: After cascading page frees up to the root, if the root had
    0 cells (interior) and right_child was set to 0, first() would try
    to read page 0 (invalid). Fixed by converting the root to a leaf
    page if it's interior with 0 cells after rebalance.

[2026-06-24] Compiler reg_zero/reg_one/reg_null registers never initialized
  - File: pysqlite/compile.py:44-46 (fixed)
  - Severity: high
  - Details: Compiler allocated register numbers 0/1/2 for zero/one/null
    constants but never emitted Integer/Null opcodes to set them. Any
    instruction referencing reg_zero (e.g., Subtract P1=reg_zero for unary
    minus) read a default NULL register. Fixed by emitting Integer/Null
    opcodes for all three constants at the start of every program.

[2026-06-24] IS NULL / IS NOT NULL compilation missing label definition
  - File: pysqlite/compile.py:277-281 (fixed)
  - Severity: high
  - Details: emit_compare_branch created a branch with an unresolved label
    (_isnull_{id}) that was never defined. The compiler emitted only one
    Integer for the false case but never defined the label for the true
    case. Fixed by restructuring with proper lbl_skip/lbl_end label pair.

[2026-06-24] SELECT * failed because _lookup_table always returned None
  - File: pysqlite/compile.py:687-688 (fixed)
  - Severity: high
  - Details: _lookup_table(cursor) unconditionally returned None, so StarExpr
    expansion in _compile_select found 0 columns and ResultRow emitted an
    empty row. Fixed by adding cursor_table dict mapping cursor→TableDef
    and returning self.cursor_table.get(cursor).

[2026-06-24] Zeroed B-Tree pages not initialized as leaf table pages
  - File: pysqlite/btree.py:28-35 (fixed)
  - Severity: high
  - Details: pager.allocate_page() zeroes new pages. BTreePage parses a 0
    page type, which is neither leaf nor interior, causing is_leaf()=False
    and the insert loop to follow right_child=0 → page 0 out of range.
    Fixed by auto-initializing zeroed pages as PT_LEAF_TABLE in __init__.

[2026-06-24] INSERT INTO ... SELECT * did not expand StarExpr
  - File: pysqlite/compile.py:594-606 (fixed)
  - Severity: high
  - Details: _compile_insert_select called compile_expr(rc.expr) for each
    result column. For StarExpr, compile_expr emits Null (placeholder) instead
    of expanding to table columns. Fixed by adding StarExpr expansion with
    Column opcodes inside _compile_insert_select.

[2026-06-24] UPDATE SET values not contiguous in registers for MakeRecord
  - File: pysqlite/compile.py:605-610 (fixed)
  - Severity: high
  - Details: After reading all column values and computing SET expressions,
    the SET value might be in a different register than the column's original
    slot. MakeRecord reads a contiguous range, so it picked up the old column
    value instead of the SET value. Fixed by adding MemCopy from SET register
    to the column's original register slot.

[2026-06-24] ORDER BY sort post-process fails when key not in SELECT list
  - File: pysqlite/compile.py:516-531, vm.py:89-117 (fixed)
  - Severity: medium
  - Details: The Sort opcode sorted result_rows by column index in the result
    row. When ORDER BY referenced a column not in the SELECT list (e.g.,
    SELECT b FROM t ORDER BY a), it picked the wrong column or fell back to
    index 0. Fixed by computing sort key expressions and appending them as
    hidden columns in the result row, sorting by those hidden columns, then
    stripping them after sort.
```


