# pysqlite — Pure Python SQLite Reimplementation

A complete SQLite database engine reimplementation in pure Python. Zero external dependencies. Reads and writes real SQLite `.db` files with full binary compatibility.

## Quick Start

```python
from pysqlite import Database

db = Database(':memory:')

db.execute("CREATE TABLE users (id INT PRIMARY KEY, name TEXT, age INT)")
db.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
db.execute("INSERT INTO users VALUES (2, 'Bob', 25)")

res = db.execute("SELECT name, age FROM users WHERE age > 28")
for row in res:
    print(row)  # ['Alice', 30]

db.close()
```

## Installation

```bash
pip install .
```

Or run directly from the repo:

```bash
PYTHONPATH=. python -c "from pysqlite import Database; print(Database(':memory:'))"
```

## CLI (Interactive REPL)

Launch the interactive SQLite shell:

```bash
# After pip install:
pysqlite

# Or directly from the repo:
python -m pysqlite.cli
python pysqlite/cli.py

# Open a specific database:
pysqlite /path/to/file.db
python -m pysqlite.cli /path/to/file.db
```

### Dot Commands

| Command | Description |
|---------|-------------|
| `.open FILE` | Open a database file |
| `.tables [PAT]` | List tables (optionally matching pattern) |
| `.schema [TABLE]` | Show CREATE statements |
| `.indexes [TABLE]` | List indexes |
| `.mode MODE` | Set output mode: `list`, `column`, `csv`, `json`, `box` |
| `.headers ON\|OFF` | Toggle column headers |
| `.separator STR` | Set field separator (default `\|`) |
| `.nullvalue STR` | Set NULL display string |
| `.timer ON\|OFF` | Toggle query timing |
| `.echo ON\|OFF` | Toggle SQL echo |
| `.databases` | List databases |
| `.show` | Show current settings |
| `.save FILE` | Save in-memory DB to file |
| `.exit` / `.quit` | Exit REPL |
| `.help` | Show help |

### Example

```
$ pysqlite
pysqlite> CREATE TABLE users (id INT, name TEXT);
pysqlite> INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob');
pysqlite> .headers on
pysqlite> .mode column
pysqlite> SELECT * FROM users;
id  | name
----|------
1   | Alice
2   | Bob
pysqlite> .exit
```

## API Reference

### Database

```python
from pysqlite import Database

db = Database(':memory:')          # In-memory database
db = Database('/path/to/file.db')  # File-backed database

result = db.execute("SELECT * FROM t")  # Execute SQL, return list of rows
db.execute("INSERT INTO t VALUES (1)")  # DML returns None for non-query

# Parameter binding (numbered and named)
db.execute("INSERT INTO t VALUES (?)", [42])
db.execute("INSERT INTO t VALUES (:val)", {'val': 42})

# Custom functions
db.create_function('DOUBLE', 1, lambda x: x * 2)
res = db.execute("SELECT DOUBLE(5)")  # [[10]]

db.close()
```

### Custom Aggregates

```python
class SumSq:
    def __init__(self):
        self.total = 0
    def step(self, value):
        if value is not None:
            self.total += value * value
    def final(self):
        return self.total

db.create_aggregate('SUMSQ', 1, SumSq)
res = db.execute("SELECT SUMSQ(val) FROM t")
```

### Connection as Context Manager

```python
with Database(':memory:') as db:
    db.execute("CREATE TABLE t (a INT)")
    db.execute("INSERT INTO t VALUES (1)")
    print(db.execute("SELECT * FROM t"))  # [[1]]
```

## Supported SQL Features

### Data Definition
| Feature | Status |
|---------|--------|
| CREATE TABLE | ✅ Full |
| CREATE TABLE ... AS SELECT | ✅ |
| CREATE TABLE ... STRICT | ✅ |
| CREATE TABLE ... WITHOUT ROWID | ✅ |
| Generated columns (VIRTUAL/STORED) | ✅ |
| Column constraints (PRIMARY KEY, NOT NULL, UNIQUE) | ✅ |
| Table constraints (PRIMARY KEY, UNIQUE, CHECK, FOREIGN KEY) | ✅ |
| CREATE INDEX / DROP INDEX | ✅ |
| CREATE VIEW / DROP VIEW | ✅ |
| CREATE TRIGGER / DROP TRIGGER | ✅ |
| CREATE VIRTUAL TABLE (fts5) | ✅ |
| ALTER TABLE RENAME TO | ✅ |
| ALTER TABLE RENAME COLUMN | ✅ |
| ALTER TABLE ADD COLUMN | ✅ |
| ALTER TABLE DROP COLUMN | ✅ |

### Data Manipulation
| Feature | Status |
|---------|--------|
| INSERT ... VALUES | ✅ |
| INSERT ... SELECT | ✅ |
| INSERT OR REPLACE | ✅ |
| INSERT OR IGNORE / ON CONFLICT DO NOTHING | ✅ |
| ON CONFLICT DO UPDATE (upsert) | ✅ |
| UPDATE ... WHERE | ✅ |
| DELETE ... WHERE | ✅ |
| RETURNING clause | ✅ |
| DEFAULT VALUES | ✅ |

### Queries
| Feature | Status |
|---------|--------|
| SELECT ... FROM | ✅ |
| WHERE, AND, OR, NOT | ✅ |
| JOIN (INNER, LEFT, CROSS) | ✅ |
| GROUP BY + HAVING | ✅ |
| ORDER BY (ASC/DESC) | ✅ |
| LIMIT / OFFSET | ✅ |
| DISTINCT | ✅ |
| Subqueries (FROM, WHERE) | ✅ |
| Common Table Expressions (WITH) | ✅ |
| Window functions (ROW_NUMBER, RANK, etc.) | ✅ |
| EXISTS / NOT EXISTS | ✅ |
| IN / NOT IN | ✅ |
| BETWEEN | ✅ |
| LIKE / GLOB | ✅ |
| CAST expressions | ✅ |
| CASE expressions | ✅ |
| UNION / INTERSECT / EXCEPT | ⚠️ Partial |

### Built-in Functions

**Scalar:**
- String: `LENGTH`, `UPPER`, `LOWER`, `SUBSTR`, `LIKE`, `GLOB`
- Math: `ABS`, `SIN`, `COS`, `TAN`, `ASIN`, `ACOS`, `ATAN`, `CEIL`, `FLOOR`, `ROUND`, `LOG`, `LOG10`, `SQRT`, `EXP`, `PI`, `POWER`, `RAND`
- Conditional: `COALESCE`, `IFNULL`, `NULLIF`
- Info: `TYPEOF`, `LAST_INSERT_ROWID`, `CHANGES`, `TOTAL_CHANGES`
- Random: `RANDOM`, `ZEROBLOB`
- Date/Time: `DATE`, `TIME`, `DATETIME`, `JULIANDAY`, `STRFTIME`, `UNIXEPOCH`
- JSON: `JSON`, `JSON_VALID`, `JSON_TYPE`, `JSON_ARRAY_LENGTH`, `JSON_EXTRACT`, `JSON_ARRAY`, `JSON_OBJECT`, `JSON_SET`, `JSON_INSERT`, `JSON_REPLACE`, `JSON_REMOVE`

**Aggregate:**
- `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `TOTAL`, `GROUP_CONCAT`
- `JSON_GROUP_ARRAY`, `JSON_GROUP_OBJECT`

### Constraints
| Feature | Status |
|---------|--------|
| PRIMARY KEY | ✅ |
| NOT NULL | ✅ (enforced on INSERT) |
| UNIQUE | ✅ |
| FOREIGN KEY | ✅ (declared, enforced on UPDATE/DELETE) |
| CHECK | ✅ |
| GENERATED ALWAYS AS | ✅ |

### Transaction Support
| Feature | Status |
|---------|--------|
| BEGIN / COMMIT / ROLLBACK | ✅ |
| SAVEPOINT / RELEASE | ✅ |
| Auto-commit mode | ✅ |
| Rollback journal (DELETE, TRUNCATE, PERSIST, MEMORY, OFF) | ✅ |
| WAL mode | ✅ |

### PRAGMAs
Implemented: `page_count`, `page_size`, `table_info`, `index_info`, `index_list`, `schema_version`, `user_version`, `application_id`, `integrity_check`, `journal_mode`, `compile_options`, `collation_list`.

## Project Structure

```
pysqlite/
├── __init__.py          # Public API (Database class)
├── ast.py               # AST node definitions
├── btree.py             # B-Tree engine
├── cell.py              # Cell serialization
├── compile.py           # SQL → bytecode compiler
├── functions/           # Built-in function implementations
│   ├── __init__.py      # Function registry
│   ├── scalar.py        # Scalar functions
│   ├── aggregate.py     # Aggregate functions
│   ├── datetime.py      # Date/time functions
│   ├── json.py          # JSON functions
│   ├── math.py          # Math functions
│   ├── window.py        # Window functions
│   └── fts.py           # FTS functions
├── jsonpath.py          # JSON path evaluation
├── lexer.py             # SQL tokenizer
├── opcode.py            # VDBE instruction set
├── pager.py             # Page cache, journal, ACID
├── parser.py            # Recursive descent SQL parser
├── record.py            # SQLite record encoding
├── schema.py            # Schema manager
├── transaction.py       # Transaction manager
├── trigram.py           # Trigram tokenizer (FTS)
├── virtualtables/       # Virtual table implementations
│   ├── __init__.py      # Virtual table framework
│   ├── fts5.py          # Full-text search
│   ├── series.py        # generate_series
│   └── json_each.py     # json_each / json_tree
├── vfs.py               # Virtual file system
└── vm.py                # Bytecode interpreter (VDBE)
```

## Running Tests

```bash
# Full test suite
pytest tests/

# Specific test file
pytest tests/sql/test_select.py

# With verbose output
pytest tests/ -v

# Stop on first failure
pytest tests/ -x --tb=short
```

## Known Limitations

- Recursive CTEs not supported
- ATTACH/DETACH DATABASE not implemented
- Windows file locking uses a workaround (some lock tests skipped)
- B-Tree overflow cells not supported (payload must fit within a page)
- Full PRAGMA coverage incomplete (~25 missing)
- Interleaved interior page splitting not fully robust

## License

MIT
