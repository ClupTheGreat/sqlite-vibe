"""Interactive SQLite REPL (command-line interface)."""

import os
import sys
import time
import csv
import io
import json


class CLI:
    """Interactive command-line REPL for pysqlite."""

    def __init__(self, db=None):
        self.db = db
        self.history_file = os.path.expanduser('~/.pysqlite_history')
        self.mode = 'list'
        self.headers = True
        self.separator = '|'
        self.null_value = ''
        self.timer = False
        self.echo = False
        self.prompt = 'pysqlite> '
        self.continue_prompt = '   ...> '

    def run(self):
        """Main REPL loop."""
        try:
            import readline
            try:
                readline.read_history_file(self.history_file)
            except (FileNotFoundError, OSError):
                pass
        except ImportError:
            pass

        while True:
            try:
                line = input(self.prompt).strip()
            except (KeyboardInterrupt, EOFError):
                print()
                break

            if not line:
                continue
            if line.startswith('.'):
                self._handle_dot_command(line[1:])
            else:
                self._execute_sql(line)

        try:
            import readline
            try:
                readline.write_history_file(self.history_file)
            except OSError:
                pass
        except ImportError:
            pass

    def _execute_sql(self, sql: str):
        """Execute SQL and display results."""
        from pysqlite.errors import DatabaseError as PysqliteDbError
        start = time.time()
        try:
            result = self.db.execute(sql)
        except PysqliteDbError as e:
            print(f"Error: {e}")
            return
        except Exception as e:
            print(f"Unexpected error: {e}")
            return
        elapsed = time.time() - start

        if isinstance(result, list) and result and isinstance(result[0], list):
            self._display_results(result)
        elif isinstance(result, list):
            pass

        if self.timer:
            print(f"Time: {elapsed:.3f}s")
        if self.echo:
            if isinstance(result, list):
                print(f"Rows affected: {len(result)}")
            else:
                print(f"Done")

    def _display_results(self, result):
        """Format and display query results based on current mode."""
        columns = getattr(result, 'columns', None) if hasattr(result, 'columns') else None
        rows = list(result)

        if self.mode == 'list':
            self._display_list(rows, columns)
        elif self.mode == 'column':
            self._display_column(rows, columns)
        elif self.mode == 'csv':
            self._display_csv(rows, columns)
        elif self.mode == 'json':
            self._display_json(rows, columns)
        elif self.mode == 'box':
            self._display_box(rows, columns)
        elif self.mode == 'insert':
            self._display_insert(rows, columns)
        else:
            self._display_list(rows, columns)

    def _display_list(self, rows, columns):
        if self.headers and columns:
            print(self.separator.join(columns))
        for row in rows:
            vals = [str(v) if v is not None else self.null_value for v in row]
            print(self.separator.join(vals))

    def _display_column(self, rows, columns):
        if not rows:
            return
        if not columns:
            columns = [f'col{i}' for i in range(len(rows[0]))]
        col_widths = [len(c) for c in columns]
        for row in rows:
            for i, v in enumerate(row):
                s = str(v) if v is not None else self.null_value
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(s))
                else:
                    col_widths.append(len(s))
        sep = '  '
        if self.headers:
            hdr = sep.join(c.ljust(w) for c, w in zip(columns, col_widths))
            print(hdr)
            print(sep.join('-' * w for w in col_widths))
        for row in rows:
            parts = []
            for i, v in enumerate(row):
                s = str(v) if v is not None else self.null_value
                w = col_widths[i] if i < len(col_widths) else len(s)
                parts.append(s.ljust(w))
            print(sep.join(parts))

    def _display_csv(self, rows, columns):
        buf = io.StringIO()
        w = csv.writer(buf)
        if self.headers and columns:
            w.writerow(columns)
        for row in rows:
            w.writerow([v if v is not None else self.null_value for v in row])
        sys.stdout.write(buf.getvalue())

    def _display_json(self, rows, columns):
        if not columns:
            columns = [f'col{i}' for i in range(len(rows[0]))] if rows else []
        data = []
        for row in rows:
            obj = {}
            for i, v in enumerate(row):
                key = columns[i] if i < len(columns) else f'col{i}'
                obj[key] = v
            data.append(obj)
        print(json.dumps(data, default=str))

    def _display_box(self, rows, columns):
        if not rows:
            return
        if not columns:
            columns = [f'col{i}' for i in range(len(rows[0]))]
        col_widths = [len(c) for c in columns]
        for row in rows:
            for i, v in enumerate(row):
                s = str(v) if v is not None else self.null_value
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(s))
                else:
                    col_widths.append(len(s))
        def hline():
            print('+' + '+'.join('-' * (w + 2) for w in col_widths) + '+')
        hline()
        if self.headers:
            parts = []
            for c, w in zip(columns, col_widths):
                parts.append(f' {c.ljust(w)} ')
            print('|' + '|'.join(parts) + '|')
            hline()
        for row in rows:
            parts = []
            for i, v in enumerate(row):
                s = str(v) if v is not None else self.null_value
                w = col_widths[i] if i < len(col_widths) else len(s)
                parts.append(f' {s.ljust(w)} ')
            print('|' + '|'.join(parts) + '|')
        hline()

    def _display_insert(self, rows, columns):
        if not rows:
            return
        table_name = getattr(self, '_insert_table', 't')
        for row in rows:
            vals = ', '.join(
                repr(v) if isinstance(v, str) else str(v) if v is not None else 'NULL'
                for v in row
            )
            print(f'INSERT INTO {table_name} VALUES ({vals});')

    def _handle_dot_command(self, cmd: str):
        parts = cmd.strip().split()
        if not parts:
            return
        cmd_name = parts[0].lower()
        args = parts[1:]

        handlers = {
            'exit': self._cmd_exit,
            'quit': self._cmd_exit,
            '.exit': self._cmd_exit,
            '.quit': self._cmd_exit,
            'open': self._cmd_open,
            'tables': self._cmd_tables,
            'schema': self._cmd_schema,
            'indexes': self._cmd_indexes,
            'mode': self._cmd_mode,
            'headers': self._cmd_headers,
            'separator': self._cmd_separator,
            'nullvalue': self._cmd_nullvalue,
            'timer': self._cmd_timer,
            'echo': self._cmd_echo,
            'databases': self._cmd_databases,
            'help': self._cmd_help,
            'show': self._cmd_show,
            'save': self._cmd_save,
        }
        handler = handlers.get(cmd_name)
        if handler:
            handler(args)
        else:
            print(f'Error: unknown command or error: .{cmd}')

    def _cmd_exit(self, args):
        sys.exit(0)

    def _cmd_open(self, args):
        from pysqlite import Database
        path = args[0] if args else ':memory:'
        self.db = Database(path)

    def _cmd_tables(self, args):
        if not self.db or not self.db.schema:
            return
        pattern = args[0].lower() if args else None
        for name in sorted(self.db.schema.tables.keys()):
            if pattern and pattern not in name.lower():
                continue
            print(name)

    def _cmd_schema(self, args):
        if not self.db or not self.db.schema:
            return
        table = args[0] if args else None
        if table:
            for td in self.db.schema.tables.values():
                if td.name.lower() == table.lower() and td.sql:
                    print(f'{td.sql};')
            for idx in self.db.schema.indexes.values():
                if idx.table_name.lower() == table.lower() and idx.sql:
                    print(f'{idx.sql};')
            for vd in self.db.schema.views.values():
                if vd.name.lower() == table.lower() and hasattr(vd, 'sql') and vd.sql:
                    print(f'{vd.sql};')
        else:
            for td in self.db.schema.tables.values():
                if td.sql:
                    print(f'{td.sql};')
            for idx in self.db.schema.indexes.values():
                if idx.sql:
                    print(f'{idx.sql};')
            for vd in self.db.schema.views.values():
                if hasattr(vd, 'sql') and vd.sql:
                    print(f'{vd.sql};')

    def _cmd_indexes(self, args):
        if not self.db or not self.db.schema:
            return
        table = args[0] if args else None
        indexes = list(self.db.schema.indexes.values())
        if table:
            for idx in indexes:
                if idx.table_name.lower() == table.lower():
                    print(idx.name)
        else:
            for idx in indexes:
                print(idx.name)

    def _cmd_mode(self, args):
        if args:
            self.mode = args[0]
        else:
            print(self.mode)

    def _cmd_headers(self, args):
        if args:
            self.headers = args[0].upper() == 'ON'
        else:
            print('ON' if self.headers else 'OFF')

    def _cmd_separator(self, args):
        if args:
            self.separator = args[0]

    def _cmd_nullvalue(self, args):
        if args:
            self.null_value = args[0]

    def _cmd_timer(self, args):
        if args:
            self.timer = args[0].upper() == 'ON'
        else:
            print('ON' if self.timer else 'OFF')

    def _cmd_echo(self, args):
        if args:
            self.echo = args[0].upper() == 'ON'
        else:
            print('ON' if self.echo else 'OFF')

    def _cmd_databases(self, args):
        res = self.db.execute("PRAGMA database_list")
        for row in res:
            print(f'{row[0]}|{row[1]}|{row[2]}')

    def _cmd_save(self, args):
        if not args:
            print('Usage: .save FILE')
            return
        src = self.db.pager.handle
        src_vfs = self.db.pager.vfs
        data = src_vfs.read(src, 0, src_vfs.file_size(src))
        from pysqlite.vfs import OSVFS
        dst_vfs = OSVFS()
        dst = dst_vfs.open(args[0], 2)
        dst_vfs.write(dst, 0, data)
        dst_vfs.close(dst)
        print(f'Saved to {args[0]}')

    def _cmd_show(self, args):
        print(f'{"mode":12}: {self.mode}')
        print(f'{"headers":12}: {"ON" if self.headers else "OFF"}')
        print(f'{"separator":12}: {self.separator}')
        print(f'{"nullvalue":12}: {self.null_value}')
        print(f'{"timer":12}: {"ON" if self.timer else "OFF"}')
        print(f'{"echo":12}: {"ON" if self.echo else "OFF"}')

    def _cmd_help(self, args):
        print("""
Commands:
  .open FILE       Open database file
  .tables [PAT]    List tables matching pattern
  .schema [TABLE]  Show CREATE statements
  .indexes [TABLE] List indexes
  .mode MODE       Set output mode (list, column, csv, json, box)
  .headers ON|OFF  Toggle column headers
  .separator STR   Set field separator (default |)
  .nullvalue STR   Set NULL display string
  .timer ON|OFF    Toggle query timer
  .echo ON|OFF     Toggle SQL echo
  .databases       List attached databases
  .show            Show current settings
  .save FILE       Save in-memory DB to file
  .exit / .quit    Exit REPL
  .help            Show this help
""")


def main():
    """Entry point for the CLI."""
    from pysqlite import Database
    path = sys.argv[1] if len(sys.argv) > 1 else ':memory:'
    db = Database(path)
    cli = CLI(db)
    cli.run()


if __name__ == '__main__':
    main()
