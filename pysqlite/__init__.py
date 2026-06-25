"""pysqlite - A complete SQLite reimplementation in pure Python."""

__version__ = "0.1.0"


class DatabaseError(Exception):
    pass


class QueryResult(list):
    """Result of a SQL query. Behaves like list[list] but also has .columns."""
    def __init__(self, rows=(), columns=None):
        super().__init__(rows)
        self.columns = list(columns) if columns else []


class Database:
    """End-to-end database interface: SQL in, results out."""

    def __init__(self, path: str):
        from pysqlite.vfs import OSVFS, MemoryVFS
        from pysqlite.pager import Pager
        from pysqlite.schema import Schema
        from pysqlite.transaction import TransactionManager

        self.vfs = MemoryVFS() if path == ':memory:' else OSVFS()
        self.pager = Pager(self.vfs, path)
        self.schema = Schema(self.pager)
        self.schema.load()
        self.tx = TransactionManager(self.pager, self.vfs, self.pager.handle, schema=self.schema)
        self._custom_functions: dict[str, callable] = {}
        self._custom_aggregates: dict[str, callable] = {}
        self._busy_handler: callable | None = None
        self._busy_timeout: int = 0

    def create_function(self, name: str, nargs: int, func: callable, *, deterministic: bool = False):
        """Register a custom scalar function."""
        self._custom_functions[name.upper()] = func

    def create_aggregate(self, name: str, nargs: int, aggregate_class: type):
        """Register a custom aggregate class (must have step() and final() methods)."""
        self._custom_aggregates[name.upper()] = aggregate_class

    def busy_handler(self, handler):
        """Register a busy handler callback for lock conflicts."""
        self._busy_handler = handler

    def busy_timeout(self, timeout_ms: int):
        """Set a busy timeout in milliseconds."""
        self._busy_timeout = timeout_ms

    def execute(self, sql: str):
        return self.execute_params(sql)

    def execute_params(self, sql: str, params: dict | None = None):
        from pysqlite.lexer import Lexer
        from pysqlite.parser import Parser
        from pysqlite.compile import Compiler
        from pysqlite.vm import VM
        from pysqlite.ast import (
            Insert, Update, Delete, Begin, Commit, RollbackStmt,
            Select, CreateVirtualTable, CreateTable, DropTable,
            Literal, ColumnRef, BinaryOp,
        )
        from pysqlite.transaction import TransactionState
        from pysqlite.virtualtables import create_virtual_table, drop_virtual_table
        from pysqlite.virtualtables import get_virtual_table

        lexer = Lexer(sql)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        statements = parser.parse()

        results = []
        for stmt in statements:
            table_name = None
            event = None
            if isinstance(stmt, Insert):
                event = 'INSERT'
                table_name = stmt.table.name if hasattr(stmt.table, 'name') else str(stmt.table)
            elif isinstance(stmt, Update):
                event = 'UPDATE'
                table_name = stmt.table.name if hasattr(stmt.table, 'name') else str(stmt.table)
            elif isinstance(stmt, Delete):
                event = 'DELETE'
                table_name = stmt.table.name if hasattr(stmt.table, 'name') else str(stmt.table)
            elif isinstance(stmt, Select) and stmt.from_clause:
                tbl = stmt.from_clause[0]
                table_name = tbl.name if hasattr(tbl, 'name') else str(tbl)

            # ── Handle CREATE VIRTUAL TABLE ──
            if isinstance(stmt, CreateVirtualTable):
                col_names = [a for a in stmt.args if not a.startswith('tokenize=')]
                content_cols = ', '.join(f'{c} TEXT' for c in col_names)
                content_sql = f'CREATE TABLE {stmt.name.name}_content (docid INTEGER PRIMARY KEY, {content_cols})'
                self.execute(content_sql)
                vt = create_virtual_table(stmt.name.name, stmt.module, stmt.args, self.schema)
                self.tx.commit()
                results.append(QueryResult([[0]]))
                continue

            # Handle SELECT on FTS5 tables with MATCH
            vt_name = table_name.upper() if table_name else None
            vt = self.schema.virtual_tables.get(vt_name) if vt_name else None

            if vt and isinstance(stmt, Select):
                col_names = vt.columns
                cols_sql = ', '.join(col_names)
                if stmt.where:
                    match_docids = self._handle_fts5_match(stmt.where, vt)
                    if match_docids is not None:
                        if match_docids:
                            ids_str = ', '.join(str(d) for d in sorted(match_docids))
                            final_sql = f'SELECT {cols_sql} FROM {vt.name}_content WHERE docid IN ({ids_str})'
                            result = self.execute(final_sql)
                            results.append(result if isinstance(result, QueryResult) else QueryResult())
                            continue
                        else:
                            results.append(QueryResult())
                            continue
                # No MATCH or no WHERE — full scan
                final_sql = f'SELECT {cols_sql} FROM {vt.name}_content'
                result = self.execute(final_sql)
                results.append(result if isinstance(result, QueryResult) else QueryResult())
                continue

            # Handle INSERT on FTS5 tables
            if vt and isinstance(stmt, Insert):
                col_names = vt.columns
                for row in (stmt.values or []):
                    vals = []
                    for v in row:
                        if isinstance(v, Literal):
                            val = v.value
                        else:
                            val = str(v)
                        if isinstance(val, str):
                            vals.append(f"'{val}'")
                        elif val is None:
                            vals.append('NULL')
                        else:
                            vals.append(str(val))
                    lit_sql = ', '.join(vals)
                    cols_sql = ', '.join(col_names)
                    content_sql = f'INSERT INTO {vt.name}_content ({cols_sql}) VALUES ({lit_sql})'
                    self.execute(content_sql)
                    docid = getattr(self.tx, '_last_rowid', 0)
                    if docid:
                        actual_vals = [v.value if isinstance(v, Literal) else str(v) for v in row]
                        vt.insert(docid, actual_vals)
                results.append(QueryResult([[0]]))
                continue

            was_in_tx = self.tx.state != TransactionState.NONE

            # Find matching triggers on this table
            before_triggers = []
            after_triggers = []
            if event and table_name:
                for t in self.schema.triggers.values():
                    if t.table_name.upper() == table_name.upper() and t.event == event:
                        if t.time in ('BEFORE', 'INSTEAD OF'):
                            before_triggers.append(t)
                        elif t.time == 'AFTER':
                            after_triggers.append(t)

            compiler = Compiler(self.schema, self.pager,
                                custom_aggregates=set(self._custom_aggregates.keys()))
            program = compiler.compile(stmt)
            columns = compiler.result_columns

            vm = VM(self.pager, self.tx,
                    custom_functions=self._custom_functions,
                    custom_aggregates=self._custom_aggregates)

            # Run BEFORE triggers
            for trig in before_triggers:
                for prog in trig.programs:
                    vm.run(prog, params=params)

            # Run main statement
            rows = vm.run(program, params=params)
            results.append(QueryResult(rows, columns=columns))
            self.tx._last_rowid = vm.last_rowid

            # Run AFTER triggers
            for trig in after_triggers:
                for prog in trig.programs:
                    vm.run(prog, params=params)

            # Auto-commit implicit transactions (skip explicit tx control statements)
            if not was_in_tx and self.tx.state != TransactionState.NONE \
               and not isinstance(stmt, (Begin, Commit, RollbackStmt)):
                self.tx.commit()

        return results if len(results) != 1 else results[0]

    def _handle_fts5_match(self, where_expr, vt) -> set | None:
        """Extract MATCH query from WHERE expression and evaluate.
        Returns set of docids or None if no MATCH found."""
        from pysqlite.ast import BinaryOp
        if isinstance(where_expr, BinaryOp) and where_expr.op == 'MATCH':
            right = where_expr.right
            query = right.value if hasattr(right, 'value') else str(right)
            if hasattr(vt, 'match'):
                return vt.match(str(query))
        elif isinstance(where_expr, BinaryOp) and where_expr.op == 'AND':
            left_set = self._handle_fts5_match(where_expr.left, vt)
            right_set = self._handle_fts5_match(where_expr.right, vt)
            if left_set is not None and right_set is not None:
                return left_set & right_set
            return left_set or right_set
        return None

    def close(self):
        if self.pager.handle:
            self.pager.vfs.close(self.pager.handle)
