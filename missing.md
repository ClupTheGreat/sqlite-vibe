# Missing Features and Implementation Gaps

> Inventory of everything not yet implemented, ordered by priority/severity.
> Last updated: 2026-06-25

## ✅ Recently Fixed

| Item | What was done | Status |
|------|--------------|--------|
| INSERT OR REPLACE inserts duplicate | Added SeekRowid + Delete before Insert for REPLACE action | Fixed |
| NOT NULL constraint not enforced | Added runtime Null check + Halt for `not_null` columns in INSERT | Fixed |
| Hex literal `x'0102'` parsed as string | Parser now decodes hex content into `bytes` via `bytes.fromhex()` | Fixed |
| Missing `functions/` module (entire directory) | Created `__init__.py`, `scalar.py`, `aggregate.py`, `datetime.py`, `json.py`, `math.py`, `window.py`, `fts.py` | Created |
| Unused `_call_datetime`/`_call_json_function` duplicated in vm.py | Refactored `_call_function` to delegate to `functions.scalar.call_function`, kept VM-specific overrides | Refactored |
| `compile.py` defined AGGREGATE_FUNCTIONS inline | Updated to import from `pysqlite.functions` | Fixed |
| Missing virtual tables (series, json_each) | Created `series.py` (GenerateSeries) and `json_each.py` (JsonEach/JsonTree) | Created |
| Missing stored procedures: SAVEPOINT, RELEASE | Added compiler handlers that emit Savepoint/Release opcodes | Fixed |
| Missing statements: REINDEX, VACUUM | Added Noop stubs with comments | Fixed |
| Missing `examples/demo.py` | Created basic demo | Created |
| Missing test files (compat, stress splits, fuzz splits, unit) | Created all files from project structure | Created |
| Missing test for function registry | Created `test_functions.py` with 22 tests | Created |

## Remaining Known Bugs

- WITHOUT ROWID composite PK upsert conflict not detected (no composite key seek)
- WITHOUT ROWID composite PK ORDER BY returns wrong row order
- OSVFS Windows locking hangs (lock tests skipped)
- Pager commit: `file_change_counter` increment could be lost on crash (sync ordering)

## Missing SQL Statements (parsed but no compilation)

| Statement | Parser | Compiler |
|-----------|--------|----------|
| `ATTACH DATABASE` | not parsed | not compiled |
| `DETACH DATABASE` | not parsed | not compiled |
| Recursive CTEs (`WITH RECURSIVE`) | partially parsed | not handled |

## Missing PRAGMA Implementations

Currently implemented: `page_count`, `page_size`, `table_info`, `index_info`, `index_list`, `schema_version`, `user_version`, `application_id`, `integrity_check`, `journal_mode`, `compile_options`, `collation_list`.

Still missing: `function_list`, `module_list`, `pragma_list`, `max_page_count`, `cache_size`, `cache_spill`, `mmap_size`, `journal_size_limit`, `synchronous`, `auto_vacuum`, `incremental_vacuum`, `locking_mode`, `busy_timeout`, `temp_store`, `trusted_schema`, `foreign_keys`, `defer_foreign_keys`, `recursive_triggers`, `strict`, `legacy_alter_table`, `reverse_unordered_selects`, `query_only`, `read_uncommitted`, `writable_schema`, `optimize`, `wal_checkpoint`, `quick_check`.

## B-Tree Engine Gaps

- `_promote_to_parent` doesn't check `insert_cell` return value (silently drops data when parent is full)
- Post-delete page merging — `_rebalance_after_delete` works for simple cases but doesn't redistribute cells from siblings
- `prev()` cursor — minimal/incomplete implementation
- No overflow cell support (cells with payload > ~25% of page size)
