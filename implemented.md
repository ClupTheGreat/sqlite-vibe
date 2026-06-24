# Implemented Features

> This file tracks completed features from `implementation.md`. 
> Format: `[x]` = done, `[ ]` = not started, `[-]` = in progress.

---

## Phase 0: Infrastructure & Utilities

```
[ ] 0.1 Bit-level utilities (varint, twos complement)
[ ] 0.2 Error hierarchy
[ ] 0.3 Format constants
```

## Phase 1: Storage Layer (VFS + Pager)

```
[ ] 1.1 VFS interface (OSVFS, MemoryVFS)
[ ] 1.2 Pager (page cache, read/write, flush, sync)
[ ] 1.3 Database header (init, parse)
[ ] 1.4 Rollback journal (begin, commit, rollback)
[ ] 1.5 Hot journal recovery
[ ] 1.6 Freelist management (allocate, free, pop, push)
[ ] 1.7 Cache eviction (LRU)
[ ] 1.8 WAL mode
```

## Phase 2: Record & B-Tree Engine

```
[ ] 2.1 Cell serialization (4 cell types)
[ ] 2.2 Record encoding (serial types, encode/decode)
[ ] 2.3 B-Tree page (header, pointers, freeblocks, defrag)
[ ] 2.4 B-Tree cursor (first, last, next, prev, seek)
[ ] 2.5 B-Tree insert (cell insertion, page splitting)
[ ] 2.6 B-Tree delete (cell removal, rebalancing)
[ ] 2.7 Overflow page handling
```

## Phase 3: SQL Language

```
[ ] 3.1 Lexer (all token types, comments, strings)
[ ] 3.2 Parser — DDL (CREATE TABLE/INDEX/VIEW/TRIGGER)
[ ] 3.3 Parser — DML (SELECT, INSERT, UPDATE, DELETE)
[ ] 3.4 Parser — Expressions (full precedence, CASE, CAST, subqueries)
[ ] 3.5 Parser — Joins (all types, ON, USING)
[ ] 3.6 Parser — Window definitions
[ ] 3.7 Parser — CTEs (WITH, RECURSIVE)
[ ] 3.8 Parser — UPSERT, RETURNING
[ ] 3.9 Parser — Transaction statements
[ ] 3.10 AST node classes
```

## Phase 4: Bytecode Compiler & Virtual Machine

```
[ ] 4.1 Opcode definitions (200+ opcodes)
[ ] 4.2 Query compiler — SELECT (full scan, index scan)
[ ] 4.3 Query compiler — INSERT (VALUES, SELECT, DEFAULT)
[ ] 4.4 Query compiler — UPDATE (SET, WHERE, index maintenance)
[ ] 4.5 Query compiler — DELETE (scan + delete)
[ ] 4.6 Query compiler — DDL (CREATE/DROP TABLE/INDEX)
[ ] 4.7 Expression compiler (all expression types)
[ ] 4.8 Optimizer — index selection
[ ] 4.9 Optimizer — join ordering
[ ] 4.10 VM core (register system, dispatch loop)
[ ] 4.11 VM cursor operations
[ ] 4.12 VM comparisons (SQLite type ordering)
[ ] 4.13 VM aggregation (AggStep, AggFinal)
[ ] 4.14 VM sorter (ORDER BY, DISTINCT)
[ ] 4.15 VM type affinity (5 affinity rules)
[ ] 4.16 EXPLAIN / EXPLAIN QUERY PLAN
```

## Phase 5: Schema & Catalog

```
[ ] 5.1 Schema manager (sqlite_schema load/save)
[ ] 5.2 Column affinity determination
[ ] 5.3 Collation sequences (BINARY, NOCASE, RTRIM)
[ ] 5.4 Schema versioning (cookie, VerifyCookie)
```

## Phase 6: Transaction & Concurrency

```
[ ] 6.1 Transaction manager (BEGIN/COMMIT/ROLLBACK)
[ ] 6.2 Lock protocol (5-state)
[ ] 6.3 Savepoints (nested, rollback to, release)
[ ] 6.4 Foreign key enforcement (immediate/deferred)
[ ] 6.5 CASCADE / SET NULL / SET DEFAULT / RESTRICT
[ ] 6.6 Busy handler
```

## Phase 7: Full SQL Feature Set

```
[ ] 7.1 Aggregate functions (COUNT, SUM, AVG, MIN, MAX, GROUP_CONCAT, TOTAL)
[ ] 7.2 Scalar functions (LENGTH, SUBSTR, REPLACE, TRIM, UPPER, LOWER, etc.)
[ ] 7.3 Numeric functions (ABS, ROUND, CEIL, FLOOR, TRUNC, RANDOM)
[ ] 7.4 Math functions (ACOS, SIN, COS, LOG, SQRT, PI, etc.)
[ ] 7.5 Date/time functions (DATE, TIME, DATETIME, JULIANDAY, STRFTIME)
[ ] 7.6 JSON functions (json_extract, json_set, json_array, etc.)
[ ] 7.7 Window functions (ROW_NUMBER, RANK, LAG, LEAD, NTILE, etc.)
[ ] 7.8 Views (CREATE/DROP, expansion)
[ ] 7.9 Triggers (BEFORE/AFTER/INSTEAD OF, OLD/NEW)
[ ] 7.10 UPSERT (ON CONFLICT DO NOTHING/UPDATE)
[ ] 7.11 RETURNING clause
[ ] 7.12 WITHOUT ROWID tables
[ ] 7.13 STRICT tables
[ ] 7.14 Generated columns (VIRTUAL/STORED)
[ ] 7.15 Full-text search (FTS5)
[ ] 7.16 PRAGMAs (all query/set variants)
[ ] 7.17 Integrity check
[ ] 7.18 ANALYZE (sqlite_stat1, stat4)
```

## Phase 8: CLI & Ecosystem

```
[ ] 8.1 CLI REPL (prompt, multi-line, history)
[ ] 8.2 Dot commands (.tables, .schema, .dump, .import, etc.)
[ ] 8.3 Output modes (list, column, csv, json, markdown, box, insert)
[ ] 8.4 Python DB-API 2.0 (connect, cursor, execute, fetch)
[ ] 8.5 Parameter binding (?, :name, @name, $name)
[ ] 8.6 Custom function/aggregate/collation registration
```

## Phase 9: Testing

```
[ ] 9.1 Unit tests (all modules)
[ ] 9.2 SQL integration tests (all features)
[ ] 9.3 Compatibility tests (against real sqlite3)
[ ] 9.4 Stress tests (large data, transactions)
[ ] 9.5 Fuzz tests (random SQL, corrupt DB)
[ ] 9.6 Regression tests
```

## Phase 10: Performance

```
[ ] 10.1 Python-level optimizations (__slots__, local bindings)
[ ] 10.2 B-Tree optimizations (LRU cache, bulk insert)
[ ] 10.3 Query compiler optimizations (constant folding, predicate pushdown)
[ ] 10.4 Pager optimizations (batch writes, mmap)
[ ] 10.5 WAL mode for concurrency
```
