"""pysqlite - A complete SQLite reimplementation in pure Python."""

__version__ = "0.1.0"


class DatabaseError(Exception):
    pass


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
        self.tx = TransactionManager(self.pager, self.vfs, self.pager.handle)

    def execute(self, sql: str):
        from pysqlite.lexer import Lexer
        from pysqlite.parser import Parser
        from pysqlite.compile import Compiler
        from pysqlite.vm import VM

        lexer = Lexer(sql)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        statements = parser.parse()

        results = []
        for stmt in statements:
            compiler = Compiler(self.schema, self.pager)
            program = compiler.compile(stmt)
            vm = VM(self.pager, self.tx)
            rows = vm.run(program)
            results.append(rows)

        return results if len(results) != 1 else results[0]

    def close(self):
        if self.pager.handle:
            self.pager.vfs.close(self.pager.handle)
