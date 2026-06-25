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
        from pysqlite.ast import Insert, Update, Delete, Begin, Commit, RollbackStmt
        from pysqlite.transaction import TransactionState

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

            # Run AFTER triggers
            for trig in after_triggers:
                for prog in trig.programs:
                    vm.run(prog, params=params)

            # Auto-commit implicit transactions (skip explicit tx control statements)
            if not was_in_tx and self.tx.state != TransactionState.NONE \
               and not isinstance(stmt, (Begin, Commit, RollbackStmt)):
                self.tx.commit()

        return results if len(results) != 1 else results[0]

    def close(self):
        if self.pager.handle:
            self.pager.vfs.close(self.pager.handle)
