"""Recursive descent SQL parser with one-token lookahead."""

from .lexer import TokenType, Token
from .errors import ParseError
from .ast import *


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.idx = 0

    def peek(self) -> TokenType:
        return self.tokens[self.idx].type

    def peek_token(self) -> Token:
        return self.tokens[self.idx]

    def advance(self) -> Token:
        t = self.tokens[self.idx]
        self.idx += 1
        return t

    def match(self, *types: TokenType) -> bool:
        if self.peek() in types:
            self.advance()
            return True
        return False

    def expect(self, tt: TokenType) -> Token:
        if self.peek() != tt:
            got = self.peek().name if self.peek() else 'EOF'
            raise ParseError(f"Expected {tt.name}, got {got}")
        return self.advance()

    def expect_any(self, *types: TokenType) -> Token:
        if self.peek() not in types:
            got = self.peek().name if self.peek() else 'EOF'
            expected = ', '.join(t.name for t in types)
            raise ParseError(f"Expected one of ({expected}), got {got}")
        return self.advance()

    def parse(self) -> list[Statement]:
        stmts = []
        while self.peek() != TokenType.EOF:
            stmts.append(self._parse_statement())
            self.match(TokenType.SEMI)
        return stmts

    def _parse_statement(self) -> Statement:
        tt = self.peek()
        if tt in (TokenType.EXPLAIN,):
            return self._parse_explain()
        if tt in (TokenType.BEGIN,):
            return self._parse_begin()
        if tt in (TokenType.COMMIT, TokenType.END):
            return self._parse_commit()
        if tt in (TokenType.ROLLBACK,):
            return self._parse_rollback()
        if tt in (TokenType.SAVEPOINT,):
            return self._parse_savepoint()
        if tt in (TokenType.RELEASE,):
            return self._parse_release()
        if tt in (TokenType.CREATE,):
            return self._parse_create()
        if tt in (TokenType.DROP,):
            return self._parse_drop()
        if tt in (TokenType.ALTER,):
            return self._parse_alter()
        if tt in (TokenType.SELECT, TokenType.WITH):
            return self._parse_select()
        if tt in (TokenType.INSERT,):
            return self._parse_insert()
        if tt in (TokenType.UPDATE,):
            return self._parse_update()
        if tt in (TokenType.DELETE,):
            return self._parse_delete()
        if tt in (TokenType.PRAGMA,):
            return self._parse_pragma()
        if tt in (TokenType.ANALYZE,):
            return self._parse_analyze()
        if tt in (TokenType.REINDEX,):
            return self._parse_reindex()
        if tt in (TokenType.VACUUM,):
            return self._parse_vacuum()
        raise ParseError(f"Unexpected token: {self.peek().name}")

    # ── EXPLAIN ──

    def _parse_explain(self) -> Explain:
        self.advance()
        qp = False
        if self.match(TokenType.QUERY):
            self.expect(TokenType.PLAN)
            qp = True
        stmt = self._parse_statement()
        return Explain(stmt, qp)

    # ── Transactions ──

    def _parse_begin(self) -> Begin:
        self.advance()
        mode = None
        if self.peek() in (TokenType.DEFERRED, TokenType.IMMEDIATE, TokenType.EXCLUSIVE):
            mode = self.advance().value
        return Begin(mode)

    def _parse_commit(self) -> Commit:
        self.advance()
        self.match(TokenType.TRANSACTION)
        return Commit()

    def _parse_rollback(self) -> RollbackStmt:
        self.advance()
        self.match(TokenType.TRANSACTION)
        sp = None
        if self.match(TokenType.TO):
            self.match(TokenType.SAVEPOINT)
            sp = self.expect(TokenType.IDENTIFIER).value
        return RollbackStmt(sp)

    def _parse_savepoint(self) -> Savepoint:
        self.advance()
        name = self.expect(TokenType.IDENTIFIER).value
        return Savepoint(name)

    def _parse_release(self) -> Release:
        self.advance()
        self.match(TokenType.SAVEPOINT)
        name = self.expect(TokenType.IDENTIFIER).value
        return Release(name)

    # ── CREATE ──

    def _parse_create(self) -> Statement:
        self.advance()
        temp = False
        if self.peek() in (TokenType.TEMP, TokenType.TEMPORARY):
            self.advance()
            temp = True
        tt = self.peek()
        if tt == TokenType.TABLE:
            return self._parse_create_table(temp)
        if tt in (TokenType.INDEX, TokenType.UNIQUE):
            return self._parse_create_index()
        if tt == TokenType.VIEW:
            return self._parse_create_view(temp)
        if tt == TokenType.TRIGGER:
            return self._parse_create_trigger()
        if tt == TokenType.VIRTUAL:
            return self._parse_create_virtual_table()
        raise ParseError(f"Expected TABLE/INDEX/VIEW/TRIGGER/VIRTUAL after CREATE")

    def _parse_create_table(self, temp: bool = False) -> CreateTable:
        self.advance()
        if_not_exists = False
        if self.match(TokenType.IF):
            self.expect(TokenType.NOT)
            self.expect(TokenType.EXISTS)
            if_not_exists = True
        name = self._parse_table_name()
        if self.peek() == TokenType.AS:
            self.advance()
            select = self._parse_select()
            return CreateTable(name=name, as_select=select, temp=temp, if_not_exists=if_not_exists)
        self.expect(TokenType.LPAREN)
        columns = []
        constraints = []
        while self.peek() != TokenType.RPAREN:
            if self.peek() in (TokenType.PRIMARY, TokenType.UNIQUE, TokenType.FOREIGN, TokenType.CHECK):
                constraints.append(self._parse_table_constraint())
            else:
                columns.append(self._parse_column_def())
            if self.peek() == TokenType.COMMA:
                self.advance()
        self.expect(TokenType.RPAREN)
        without_rowid = False
        strict = False
        if self.match(TokenType.WITHOUT):
            self.expect(TokenType.ROWID)
            without_rowid = True
        if self.match(TokenType.STRICT):
            strict = True
        return CreateTable(name=name, columns=columns, constraints=constraints,
                           temp=temp, if_not_exists=if_not_exists,
                           without_rowid=without_rowid, strict=strict)

    def _parse_table_name(self) -> TableName:
        schema = None
        name = self.expect(TokenType.IDENTIFIER).value
        if self.match(TokenType.DOT):
            schema = name
            name = self.expect(TokenType.IDENTIFIER).value
        return TableName(name=name, schema=schema)

    def _parse_column_def(self) -> ColumnDef:
        name = self.expect(TokenType.IDENTIFIER).value
        type_name = None
        if self.peek() == TokenType.IDENTIFIER:
            type_name = self._parse_type_name()
        constraints = []
        while self.peek() in (TokenType.PRIMARY, TokenType.NOT, TokenType.UNIQUE,
                               TokenType.CHECK, TokenType.DEFAULT, TokenType.COLLATE,
                               TokenType.REFERENCES, TokenType.GENERATED,
                               TokenType.CONSTRAINT, TokenType.AS):
            constraints.append(self._parse_column_constraint())
        return ColumnDef(name=name, type_name=type_name, constraints=constraints)

    def _parse_type_name(self) -> TypeName:
        name = self.expect(TokenType.IDENTIFIER).value
        precision = None
        scale = None
        if self.match(TokenType.LPAREN):
            precision = int(self.expect(TokenType.INTEGER).value)
            if self.match(TokenType.COMMA):
                scale = int(self.expect(TokenType.INTEGER).value)
            self.expect(TokenType.RPAREN)
        return TypeName(name=name, precision=precision, scale=scale)

    def _parse_column_constraint(self) -> ColumnConstraint:
        name = None
        if self.match(TokenType.CONSTRAINT):
            name = self.expect(TokenType.IDENTIFIER).value
        if self.match(TokenType.PRIMARY):
            self.expect(TokenType.KEY)
            self.match(TokenType.ASC)
            self.match(TokenType.DESC)
            self._parse_conflict_clause()
            self.match(TokenType.AUTOINCREMENT)
            return ColumnConstraint(name=name, kind='PRIMARY KEY')
        if self.match(TokenType.NOT):
            self.expect(TokenType.NULL)
            self._parse_conflict_clause()
            return ColumnConstraint(name=name, kind='NOT NULL')
        if self.match(TokenType.UNIQUE):
            self._parse_conflict_clause()
            return ColumnConstraint(name=name, kind='UNIQUE')
        if self.match(TokenType.CHECK):
            self.expect(TokenType.LPAREN)
            expr = self._parse_expr()
            self.expect(TokenType.RPAREN)
            return ColumnConstraint(name=name, kind='CHECK', details=expr)
        if self.match(TokenType.DEFAULT):
            val = self._parse_default_value()
            return ColumnConstraint(name=name, kind='DEFAULT', details=val)
        if self.match(TokenType.COLLATE):
            coll = self.expect(TokenType.IDENTIFIER).value
            return ColumnConstraint(name=name, kind='COLLATE', details=coll)
        if self.match(TokenType.REFERENCES):
            fk = self._parse_foreign_key()
            return ColumnConstraint(name=name, kind='REFERENCES', details=fk)
        if self.match(TokenType.GENERATED):
            self.match(TokenType.ALWAYS)
            self.expect(TokenType.AS)
            self.expect(TokenType.LPAREN)
            expr = self._parse_expr()
            self.expect(TokenType.RPAREN)
            storage = 'VIRTUAL'
            if self.match(TokenType.STORED):
                storage = 'STORED'
            elif self.match(TokenType.VIRTUAL_KW):
                storage = 'VIRTUAL'
            return ColumnConstraint(name=name, kind='GENERATED',
                                    details={'expr': expr, 'storage': storage})
        if self.match(TokenType.AS):
            self.expect(TokenType.LPAREN)
            expr = self._parse_expr()
            self.expect(TokenType.RPAREN)
            storage = 'VIRTUAL'
            if self.match(TokenType.STORED):
                storage = 'STORED'
            elif self.match(TokenType.VIRTUAL_KW):
                storage = 'VIRTUAL'
            return ColumnConstraint(name=name, kind='GENERATED',
                                    details={'expr': expr, 'storage': storage})
        raise ParseError("Unknown column constraint")

    def _parse_default_value(self) -> Any:
        if self.match(TokenType.NULL):
            return NullLiteral()
        if self.peek() in (TokenType.INTEGER, TokenType.FLOAT):
            return self._parse_literal()
        if self.peek() == TokenType.STRING:
            return self._parse_literal()
        if self.match(TokenType.LPAREN):
            expr = self._parse_expr()
            self.expect(TokenType.RPAREN)
            return expr
        if self.peek() == TokenType.IDENTIFIER:
            val = self.advance().value
            return val
        return self._parse_literal()

    def _parse_conflict_clause(self):
        if self.match(TokenType.ON):
            self.expect(TokenType.CONFLICT)
            self.expect_any(TokenType.ROLLBACK, TokenType.ABORT, TokenType.FAIL,
                            TokenType.IGNORE, TokenType.REPLACE)

    def _parse_foreign_key(self) -> ForeignKey:
        table = self.expect(TokenType.IDENTIFIER).value
        columns = []
        if self.match(TokenType.LPAREN):
            columns.append(self.expect(TokenType.IDENTIFIER).value)
            while self.match(TokenType.COMMA):
                columns.append(self.expect(TokenType.IDENTIFIER).value)
            self.expect(TokenType.RPAREN)
        actions = {}
        while self.peek() in (TokenType.ON, TokenType.MATCH, TokenType.DEFERRED,
                               TokenType.NOT):
            if self.match(TokenType.ON):
                action = self.expect_any(TokenType.DELETE, TokenType.UPDATE).value
                self.match(TokenType.SET)
                self.match(TokenType.NULL)
                if self.peek() == TokenType.CASCADE:
                    actions[action] = 'CASCADE'
                elif self.peek() == TokenType.RESTRICT:
                    actions[action] = 'RESTRICT'
                elif self.peek() == TokenType.SET_NULL:
                    actions[action] = 'SET NULL'
                elif self.peek() == TokenType.SET_DEFAULT:
                    actions[action] = 'SET DEFAULT'
                elif self.peek() == TokenType.NOTHING:
                    actions[action] = 'NO ACTION'
                else:
                    actions[action] = self.advance().value
            elif self.match(TokenType.MATCH):
                actions['MATCH'] = self.expect(TokenType.IDENTIFIER).value
            else:
                break
        return ForeignKey(table=table, columns=columns, actions=actions)

    def _parse_table_constraint(self) -> TableConstraint:
        name = None
        if self.match(TokenType.CONSTRAINT):
            name = self.expect(TokenType.IDENTIFIER).value
        if self.match(TokenType.PRIMARY):
            self.expect(TokenType.KEY)
            self.expect(TokenType.LPAREN)
            cols = [self.expect(TokenType.IDENTIFIER).value]
            while self.match(TokenType.COMMA):
                cols.append(self.expect(TokenType.IDENTIFIER).value)
            self.expect(TokenType.RPAREN)
            self._parse_conflict_clause()
            return TableConstraint(name=name, kind='PRIMARY KEY', columns=cols)
        if self.match(TokenType.UNIQUE):
            self.expect(TokenType.LPAREN)
            cols = [self.expect(TokenType.IDENTIFIER).value]
            while self.match(TokenType.COMMA):
                cols.append(self.expect(TokenType.IDENTIFIER).value)
            self.expect(TokenType.RPAREN)
            self._parse_conflict_clause()
            return TableConstraint(name=name, kind='UNIQUE', columns=cols)
        if self.match(TokenType.CHECK):
            self.expect(TokenType.LPAREN)
            expr = self._parse_expr()
            self.expect(TokenType.RPAREN)
            return TableConstraint(name=name, kind='CHECK', expr=expr)
        if self.match(TokenType.FOREIGN):
            self.expect(TokenType.KEY)
            self.expect(TokenType.LPAREN)
            cols = [self.expect(TokenType.IDENTIFIER).value]
            while self.match(TokenType.COMMA):
                cols.append(self.expect(TokenType.IDENTIFIER).value)
            self.expect(TokenType.RPAREN)
            self.expect(TokenType.REFERENCES)
            fk = self._parse_foreign_key()
            fk.columns = cols
            return TableConstraint(name=name, kind='FOREIGN KEY', details=fk)
        raise ParseError("Expected table constraint")

    def _parse_create_index(self) -> CreateIndex:
        unique = False
        if self.match(TokenType.UNIQUE):
            unique = True
        self.expect(TokenType.INDEX)
        if_not_exists = False
        if self.match(TokenType.IF):
            self.expect(TokenType.NOT)
            self.expect(TokenType.EXISTS)
            if_not_exists = True
        schema = None
        name = self.expect(TokenType.IDENTIFIER).value
        if self.match(TokenType.DOT):
            schema = name
            name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.ON)
        table = self._parse_table_name()
        self.expect(TokenType.LPAREN)
        columns = [self._parse_ordering_term()]
        while self.match(TokenType.COMMA):
            columns.append(self._parse_ordering_term())
        self.expect(TokenType.RPAREN)
        where = None
        if self.match(TokenType.WHERE):
            where = self._parse_expr()
        return CreateIndex(name=name, table=table, columns=columns,
                           unique=unique, if_not_exists=if_not_exists,
                           where=where, schema=schema)

    def _parse_create_view(self, temp: bool = False) -> CreateView:
        self.advance()
        if_not_exists = False
        if self.match(TokenType.IF):
            self.expect(TokenType.NOT)
            self.expect(TokenType.EXISTS)
            if_not_exists = True
        name = self._parse_table_name()
        self.expect(TokenType.AS)
        select = self._parse_select()
        return CreateView(name=name, select=select, temp=temp, if_not_exists=if_not_exists)

    def _parse_create_trigger(self) -> CreateTrigger:
        time = 'BEFORE'
        if self.match(TokenType.BEFORE):
            time = 'BEFORE'
        elif self.match(TokenType.AFTER):
            time = 'AFTER'
        elif self.match(TokenType.INSTEAD):
            self.expect(TokenType.OF)
            time = 'INSTEAD OF'
        event = self.expect_any(TokenType.INSERT, TokenType.UPDATE, TokenType.DELETE).value
        columns = []
        if self.match(TokenType.LPAREN):
            columns.append(self.expect(TokenType.IDENTIFIER).value)
            while self.match(TokenType.COMMA):
                columns.append(self.expect(TokenType.IDENTIFIER).value)
            self.expect(TokenType.RPAREN)
        self.expect(TokenType.ON)
        table = self.expect(TokenType.IDENTIFIER).value
        for_each_row = False
        if self.match(TokenType.FOR):
            self.expect(TokenType.EACH)
            self.expect(TokenType.ROW)
            for_each_row = True
        when = None
        if self.match(TokenType.WHEN):
            when = self._parse_expr()
        stmts = []
        self.expect(TokenType.BEGIN)
        while self.peek() not in (TokenType.END, TokenType.EOF):
            stmts.append(self._parse_statement())
            self.match(TokenType.SEMI)
        self.expect(TokenType.END)
        return CreateTrigger(name='', table=table, statements=stmts,
                             time=time, event=event, columns=columns,
                             for_each_row=for_each_row, when=when)

    def _parse_create_virtual_table(self) -> CreateVirtualTable:
        if self.peek() == TokenType.TABLE:
            self.advance()
        if_not_exists = False
        if self.match(TokenType.IF):
            self.expect(TokenType.NOT)
            self.expect(TokenType.EXISTS)
            if_not_exists = True
        name = self._parse_table_name()
        self.expect(TokenType.USING)
        module = self.expect(TokenType.IDENTIFIER).value
        args = []
        if self.match(TokenType.LPAREN):
            while self.peek() != TokenType.RPAREN:
                args.append(self.advance().value)
            self.expect(TokenType.RPAREN)
        return CreateVirtualTable(name=name, module=module, args=args,
                                  if_not_exists=if_not_exists)

    # ── DROP ──

    def _parse_drop(self) -> Statement:
        self.advance()
        tt = self.peek()
        if tt == TokenType.TABLE:
            return self._parse_drop_table()
        if tt == TokenType.INDEX:
            return self._parse_drop_index()
        if tt == TokenType.VIEW:
            return self._parse_drop_view()
        if tt == TokenType.TRIGGER:
            return self._parse_drop_trigger()
        raise ParseError("Expected TABLE/INDEX/VIEW/TRIGGER after DROP")

    def _parse_drop_table(self) -> DropTable:
        self.advance()
        if_exists = False
        if self.match(TokenType.IF):
            self.expect(TokenType.EXISTS)
            if_exists = True
        name = self._parse_table_name()
        return DropTable(name=name, if_exists=if_exists)

    def _parse_drop_index(self) -> DropIndex:
        self.advance()
        if_exists = False
        if self.match(TokenType.IF):
            self.expect(TokenType.EXISTS)
            if_exists = True
        schema = None
        name = self.expect(TokenType.IDENTIFIER).value
        if self.match(TokenType.DOT):
            schema = name
            name = self.expect(TokenType.IDENTIFIER).value
        return DropIndex(name=name, if_exists=if_exists, schema=schema)

    def _parse_drop_view(self) -> DropView:
        self.advance()
        if_exists = False
        if self.match(TokenType.IF):
            self.expect(TokenType.EXISTS)
            if_exists = True
        schema = None
        name = self.expect(TokenType.IDENTIFIER).value
        if self.match(TokenType.DOT):
            schema = name
            name = self.expect(TokenType.IDENTIFIER).value
        return DropView(name=name, if_exists=if_exists, schema=schema)

    def _parse_drop_trigger(self) -> DropTrigger:
        self.advance()
        if_exists = False
        if self.match(TokenType.IF):
            self.expect(TokenType.EXISTS)
            if_exists = True
        schema = None
        name = self.expect(TokenType.IDENTIFIER).value
        if self.match(TokenType.DOT):
            schema = name
            name = self.expect(TokenType.IDENTIFIER).value
        return DropTrigger(name=name, if_exists=if_exists, schema=schema)

    # ── ALTER ──

    def _parse_alter(self) -> AlterTable:
        self.advance()
        self.expect(TokenType.TABLE)
        table = self._parse_table_name()
        action = ''
        new_name = None
        column = None
        new_column = None
        column_def = None
        if self.match(TokenType.ADD):
            self.match(TokenType.COLUMN)
            action = 'ADD COLUMN'
            column_def = self._parse_column_def()
        elif self.match(TokenType.DROP):
            self.match(TokenType.COLUMN)
            action = 'DROP COLUMN'
            column = self.expect(TokenType.IDENTIFIER).value
        elif self.match(TokenType.RENAME):
            if self.match(TokenType.TO):
                action = 'RENAME TO'
                new_name = self.expect(TokenType.IDENTIFIER).value
            elif self.match(TokenType.COLUMN):
                action = 'RENAME COLUMN'
                column = self.expect(TokenType.IDENTIFIER).value
                self.expect(TokenType.TO)
                new_name = self.expect(TokenType.IDENTIFIER).value
        return AlterTable(table=table, action=action, new_name=new_name,
                          column=column, new_column=new_column,
                          column_def=column_def)

    # ── SELECT ──

    def _parse_select(self) -> Select:
        ctes = []
        if self.peek() == TokenType.WITH:
            ctes = self._parse_cte()
        self.expect(TokenType.SELECT)
        distinct = self.match(TokenType.DISTINCT)
        self.match(TokenType.ALL)
        columns = [self._parse_result_column()]
        while self.match(TokenType.COMMA):
            columns.append(self._parse_result_column())
        from_clause = []
        if self.match(TokenType.FROM):
            from_clause.append(self._parse_table_ref())
            while self.match(TokenType.COMMA):
                from_clause.append(self._parse_table_ref())
        where = None
        if self.match(TokenType.WHERE):
            where = self._parse_expr()
        group_by = []
        having = None
        if self.match(TokenType.GROUP):
            self.expect(TokenType.BY)
            group_by.append(self._parse_expr())
            while self.match(TokenType.COMMA):
                group_by.append(self._parse_expr())
            if self.match(TokenType.HAVING):
                having = self._parse_expr()
        window = []
        if self.match(TokenType.WINDOW):
            window.append(self._parse_window_def())
            while self.match(TokenType.COMMA):
                window.append(self._parse_window_def())
        compound_op = None
        compound_select = None
        if self.peek() in (TokenType.UNION, TokenType.INTERSECT, TokenType.EXCEPT):
            compound_op = self.advance().value
            self.match(TokenType.ALL)
            compound_select = self._parse_select()
        order_by = []
        if self.match(TokenType.ORDER):
            self.expect(TokenType.BY)
            order_by.append(self._parse_ordering_term())
            while self.match(TokenType.COMMA):
                order_by.append(self._parse_ordering_term())
        limit = None
        offset = None
        if self.match(TokenType.LIMIT):
            limit = self._parse_expr()
            if self.match(TokenType.OFFSET):
                offset = self._parse_expr()
        for_update = self.peek() == TokenType.FOR and self.tokens[self.idx + 1].type == TokenType.UPDATE
        if for_update:
            self.advance()
            self.advance()
        return Select(columns=columns, distinct=distinct, from_clause=from_clause,
                      where=where, group_by=group_by, having=having,
                      window=window, order_by=order_by, limit=limit, offset=offset,
                      ctes=ctes, compound_op=compound_op,
                      compound_select=compound_select, for_update=for_update)

    def _parse_result_column(self) -> ResultColumn:
        if self.match(TokenType.STAR):
            return ResultColumn(expr=StarExpr(), alias=None)
        expr = self._parse_expr()
        alias = None
        if self.match(TokenType.AS):
            alias = self.expect(TokenType.IDENTIFIER).value
        elif self.peek() == TokenType.IDENTIFIER:
            alias = self.advance().value
        return ResultColumn(expr=expr, alias=alias)

    def _parse_table_ref(self) -> Any:
        if self.peek() == TokenType.LPAREN:
            self.advance()
            if self.peek() == TokenType.SELECT:
                sub = self._parse_select()
                self.expect(TokenType.RPAREN)
                alias = None
                if self.match(TokenType.AS):
                    alias = self.expect(TokenType.IDENTIFIER).value
                elif self.peek() == TokenType.IDENTIFIER:
                    alias = self.advance().value
                return SubqueryTable(select=sub, alias=alias)
            table = self._parse_table_ref()
            while self.match(TokenType.COMMA):
                table = (table, self._parse_table_ref())
            self.expect(TokenType.RPAREN)
            return table
        name = self._parse_table_name()
        while self.peek() in (TokenType.JOIN, TokenType.LEFT, TokenType.RIGHT,
                               TokenType.CROSS, TokenType.NATURAL,
                               TokenType.COMMA, TokenType.INNER):
            if self.peek() == TokenType.COMMA:
                self.advance()
                next_table = self._parse_table_ref()
                return [TableName(name=name.name, schema=name.schema)] + (
                    [next_table] if not isinstance(next_table, list) else next_table)
            jc = self._parse_join()
            jc.table = TableName(name=name.name, schema=name.schema)
            return jc
        return name

    def _parse_join(self) -> JoinClause:
        natural = self.match(TokenType.NATURAL)
        join_type = ''
        outer = False
        if self.match(TokenType.LEFT):
            join_type = 'LEFT'
            outer = self.match(TokenType.OUTER)
        elif self.match(TokenType.RIGHT):
            join_type = 'RIGHT'
            outer = self.match(TokenType.OUTER)
        elif self.match(TokenType.CROSS):
            join_type = 'CROSS'
        elif self.match(TokenType.INNER):
            join_type = 'INNER'
        self.match(TokenType.OUTER)
        self.expect(TokenType.JOIN)
        table = self._parse_table_ref()
        on = None
        using = []
        if self.match(TokenType.ON):
            on = self._parse_expr()
        elif self.match(TokenType.USING):
            self.expect(TokenType.LPAREN)
            using.append(self.expect(TokenType.IDENTIFIER).value)
            while self.match(TokenType.COMMA):
                using.append(self.expect(TokenType.IDENTIFIER).value)
            self.expect(TokenType.RPAREN)
        return JoinClause(type=join_type, outer=outer, table=table,
                          on=on, using=using)

    def _parse_window_def(self) -> tuple[str, WindowDef]:
        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.AS)
        self.expect(TokenType.LPAREN)
        w = self._parse_window_spec()
        self.expect(TokenType.RPAREN)
        return (name, w)

    def _parse_window_spec(self) -> WindowDef:
        name = None
        if self.peek() == TokenType.IDENTIFIER:
            if not (self.tokens[self.idx + 1].type == TokenType.DOT or
                    self.tokens[self.idx + 1].type == TokenType.LPAREN):
                name = self.advance().value
        partition = []
        if self.match(TokenType.PARTITION):
            self.expect(TokenType.BY)
            partition.append(self._parse_expr())
            while self.match(TokenType.COMMA):
                partition.append(self._parse_expr())
        order = []
        if self.match(TokenType.ORDER):
            self.expect(TokenType.BY)
            order.append(self._parse_ordering_term())
            while self.match(TokenType.COMMA):
                order.append(self._parse_ordering_term())
        frame = None
        if self.peek() in (TokenType.ROWS, TokenType.RANGE, TokenType.GROUPS):
            unit = self.advance().value
            frame = WindowFrame(unit=unit)
            self.match(TokenType.BETWEEN)
            if self.peek() == TokenType.UNBOUNDED:
                start = 'UNBOUNDED PRECEDING'
                start_expr = None
            elif self.peek() == TokenType.CURRENT_ROW:
                start = 'CURRENT ROW'
                start_expr = None
            else:
                start = 'VALUE PRECEDING'
                start_expr = self._parse_expr()
                self.expect(TokenType.PRECEDING)
            self.expect(TokenType.AND)
            if self.peek() == TokenType.UNBOUNDED:
                end = 'UNBOUNDED FOLLOWING'
                end_expr = None
            elif self.peek() == TokenType.CURRENT_ROW:
                end = 'CURRENT ROW'
                end_expr = None
            else:
                end = 'VALUE FOLLOWING'
                end_expr = self._parse_expr()
                self.expect(TokenType.FOLLOWING)
            frame = WindowFrame(unit=unit, start=start, start_expr=start_expr,
                                end=end, end_expr=end_expr)
        return WindowDef(partition=partition, order=order, frame=frame, name=name)

    # ── INSERT ──

    def _parse_insert(self) -> Insert:
        ctes = []
        if self.peek() == TokenType.WITH:
            ctes = self._parse_cte()
        self.expect(TokenType.INSERT)
        or_action = None
        if self.match(TokenType.OR):
            or_action = self.expect_any(TokenType.ROLLBACK, TokenType.ABORT,
                                        TokenType.FAIL, TokenType.IGNORE,
                                        TokenType.REPLACE).value
        self.expect(TokenType.INTO)
        table = self._parse_table_name()
        self.match(TokenType.AS)
        columns = []
        if self.match(TokenType.LPAREN) and self.peek() != TokenType.SELECT:
            columns.append(self.expect(TokenType.IDENTIFIER).value)
            while self.match(TokenType.COMMA):
                columns.append(self.expect(TokenType.IDENTIFIER).value)
            self.expect(TokenType.RPAREN)
        values = []
        select = None
        default_values = False
        if self.match(TokenType.VALUES):
            values.append(self._parse_expr_list())
            while self.match(TokenType.COMMA):
                values.append(self._parse_expr_list())
        elif self.match(TokenType.DEFAULT):
            self.expect(TokenType.VALUES)
            default_values = True
        elif self.peek() in (TokenType.SELECT, TokenType.WITH):
            select = self._parse_select()
        on_conflict = None
        if self.match(TokenType.ON):
            self.expect(TokenType.CONFLICT)
            conflict_cols = []
            conflict_where = None
            if self.match(TokenType.LPAREN):
                conflict_cols.append(self.expect(TokenType.IDENTIFIER).value)
                while self.match(TokenType.COMMA):
                    conflict_cols.append(self.expect(TokenType.IDENTIFIER).value)
                self.expect(TokenType.RPAREN)
                if self.match(TokenType.WHERE):
                    conflict_where = self._parse_expr()
            self.expect(TokenType.DO)
            if self.match(TokenType.NOTHING):
                on_conflict = OnConflict(columns=conflict_cols, where=conflict_where,
                                         action='NOTHING')
            elif self.match(TokenType.UPDATE):
                self.expect(TokenType.SET)
                clauses = [self._parse_set_clause()]
                while self.match(TokenType.COMMA):
                    clauses.append(self._parse_set_clause())
                condition = None
                if self.match(TokenType.WHERE):
                    condition = self._parse_expr()
                on_conflict = OnConflict(columns=conflict_cols, where=conflict_where,
                                         action='UPDATE', set_clauses=clauses,
                                         condition=condition)
        returning = None
        if self.match(TokenType.RETURNING):
            returning = self._parse_returning()
        return Insert(table=table, columns=columns, values=values,
                      select=select, default_values=default_values,
                      or_action=or_action, ctes=ctes,
                      on_conflict=on_conflict, returning=returning)

    def _parse_expr_list(self) -> list[Expr]:
        self.expect(TokenType.LPAREN)
        exprs = [self._parse_expr()]
        while self.match(TokenType.COMMA):
            exprs.append(self._parse_expr())
        self.expect(TokenType.RPAREN)
        return exprs

    # ── UPDATE ──

    def _parse_update(self) -> Update:
        ctes = []
        if self.peek() == TokenType.WITH:
            ctes = self._parse_cte()
        self.expect(TokenType.UPDATE)
        or_action = None
        if self.match(TokenType.OR):
            or_action = self.expect_any(TokenType.ROLLBACK, TokenType.ABORT,
                                        TokenType.FAIL, TokenType.IGNORE,
                                        TokenType.REPLACE).value
        table = self._parse_table_name()
        self.match(TokenType.AS)
        self.expect(TokenType.SET)
        clauses = [self._parse_set_clause()]
        while self.match(TokenType.COMMA):
            clauses.append(self._parse_set_clause())
        from_clause = []
        if self.match(TokenType.FROM):
            from_clause = self._parse_table_ref()
            if not isinstance(from_clause, list):
                from_clause = [from_clause]
        where = None
        if self.match(TokenType.WHERE):
            where = self._parse_expr()
        order_by = []
        if self.match(TokenType.ORDER):
            self.expect(TokenType.BY)
            order_by.append(self._parse_ordering_term())
            while self.match(TokenType.COMMA):
                order_by.append(self._parse_ordering_term())
        limit = None
        offset = None
        if self.match(TokenType.LIMIT):
            limit = self._parse_expr()
            if self.match(TokenType.OFFSET):
                offset = self._parse_expr()
        returning = None
        if self.match(TokenType.RETURNING):
            returning = self._parse_returning()
        return Update(table=table, set_clauses=clauses, from_clause=from_clause,
                      where=where, order_by=order_by, limit=limit,
                      offset=offset, or_action=or_action, ctes=ctes,
                      returning=returning)

    def _parse_set_clause(self) -> SetClause:
        col = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.EQ)
        expr = self._parse_expr()
        return SetClause(column=col, expr=expr)

    # ── DELETE ──

    def _parse_delete(self) -> Delete:
        ctes = []
        if self.peek() == TokenType.WITH:
            ctes = self._parse_cte()
        self.expect(TokenType.DELETE)
        self.expect(TokenType.FROM)
        table = self._parse_table_name()
        self.match(TokenType.AS)
        where = None
        if self.match(TokenType.WHERE):
            where = self._parse_expr()
        order_by = []
        if self.match(TokenType.ORDER):
            self.expect(TokenType.BY)
            order_by.append(self._parse_ordering_term())
            while self.match(TokenType.COMMA):
                order_by.append(self._parse_ordering_term())
        limit = None
        offset = None
        if self.match(TokenType.LIMIT):
            limit = self._parse_expr()
            if self.match(TokenType.OFFSET):
                offset = self._parse_expr()
        returning = None
        if self.match(TokenType.RETURNING):
            returning = self._parse_returning()
        return Delete(table=table, where=where, order_by=order_by,
                      limit=limit, offset=offset, ctes=ctes, returning=returning)

    def _parse_returning(self) -> Returning:
        cols = [self._parse_result_column()]
        while self.match(TokenType.COMMA):
            cols.append(self._parse_result_column())
        return Returning(columns=cols)

    # ── CTE ──

    def _parse_cte(self) -> list[CTE]:
        self.expect(TokenType.WITH)
        recursive = self.match(TokenType.RECURSIVE)
        ctes = [self._parse_cte_table(recursive)]
        while self.match(TokenType.COMMA):
            ctes.append(self._parse_cte_table(recursive))
        return ctes

    def _parse_cte_table(self, recursive: bool) -> CTE:
        name = self.expect(TokenType.IDENTIFIER).value
        cols = []
        if self.match(TokenType.LPAREN):
            cols.append(self.expect(TokenType.IDENTIFIER).value)
            while self.match(TokenType.COMMA):
                cols.append(self.expect(TokenType.IDENTIFIER).value)
            self.expect(TokenType.RPAREN)
        self.expect(TokenType.AS)
        self.expect(TokenType.LPAREN)
        select = self._parse_select()
        self.expect(TokenType.RPAREN)
        return CTE(name=name, columns=cols, select=select, recursive=recursive)

    # ── PRAGMA / ANALYZE / REINDEX / VACUUM ──

    def _parse_pragma(self) -> Pragma:
        self.advance()
        schema = None
        name = self.expect(TokenType.IDENTIFIER).value
        if self.match(TokenType.DOT):
            schema = name
            name = self.expect(TokenType.IDENTIFIER).value
        value = None
        if self.match(TokenType.EQ):
            if self.peek() in (TokenType.IDENTIFIER, TokenType.INTEGER,
                               TokenType.FLOAT, TokenType.STRING):
                value = self.advance().value
            else:
                value = self._parse_expr()
        elif self.match(TokenType.LPAREN):
            value = self._parse_expr()
            self.expect(TokenType.RPAREN)
        return Pragma(name=name, value=value, schema=schema)

    def _parse_analyze(self) -> Analyze:
        self.advance()
        name = None
        if self.peek() != TokenType.EOF and self.peek() != TokenType.SEMI:
            name = self.advance().value
        return Analyze(name=name)

    def _parse_reindex(self) -> Reindex:
        self.advance()
        name = None
        collation = None
        if self.peek() != TokenType.EOF and self.peek() != TokenType.SEMI:
            name = self.advance().value
        return Reindex(name=name)

    def _parse_vacuum(self) -> Vacuum:
        self.advance()
        schema = None
        if self.peek() != TokenType.EOF and self.peek() != TokenType.SEMI:
            schema = self.advance().value
        return Vacuum(schema=schema)

    # ── Expression Parsing (Precedence Climbing) ──

    def _parse_expr(self) -> Expr:
        return self._parse_expr_or()

    def _parse_expr_or(self) -> Expr:
        left = self._parse_expr_and()
        while self.match(TokenType.OR):
            right = self._parse_expr_and()
            left = BinaryOp('OR', left, right)
        return left

    def _parse_expr_and(self) -> Expr:
        left = self._parse_expr_not()
        while self.match(TokenType.AND):
            right = self._parse_expr_not()
            left = BinaryOp('AND', left, right)
        return left

    def _parse_expr_not(self) -> Expr:
        if self.match(TokenType.NOT):
            return UnaryOp('NOT', self._parse_expr_not())
        return self._parse_expr_isnull()

    def _parse_expr_isnull(self) -> Expr:
        left = self._parse_exr_comparison()
        while True:
            if self.match(TokenType.IS):
                negated = self.match(TokenType.NOT)
                if self.match(TokenType.NULL):
                    left = IsNullOp(left, negated=negated)
                else:
                    right = self._parse_exr_comparison()
                    left = IsOp(left, right, negated=negated)
            elif self.peek() == TokenType.NOT:
                save = self.idx
                self.advance()
                if self.match(TokenType.NULL):
                    left = IsNullOp(left, negated=True)
                else:
                    self.idx = save
                    break
            elif self.match(TokenType.NULL):
                left = IsNullOp(left, negated=False)
            else:
                break
        return left

    def _parse_exr_comparison(self) -> Expr:
        left = self._parse_expr_between()
        while self.peek() in (TokenType.LIKE, TokenType.GLOB, TokenType.MATCH,
                               TokenType.REGEXP, TokenType.IN, TokenType.NOT):
            if self.peek() == TokenType.NOT:
                self.advance()
                if self.peek() == TokenType.IN:
                    return self._parse_in_op(left, negated=True)
                elif self.peek() == TokenType.LIKE:
                    return self._parse_like_op(left, negated=True)
                elif self.peek() == TokenType.GLOB:
                    right = self._parse_expr_between()
                    escape = None
                    if self.match(TokenType.ESCAPE):
                        escape = self._parse_expr_between()
                    return BinaryOp('NOT GLOB', left, right)
                elif self.peek() == TokenType.MATCH:
                    right = self._parse_expr_between()
                    return BinaryOp('NOT MATCH', left, right)
                elif self.peek() == TokenType.REGEXP:
                    right = self._parse_expr_between()
                    return BinaryOp('NOT REGEXP', left, right)
            elif self.peek() == TokenType.IN:
                return self._parse_in_op(left, negated=False)
            elif self.peek() == TokenType.LIKE:
                return self._parse_like_op(left, negated=False)
            elif self.peek() == TokenType.GLOB:
                right = self._parse_expr_between()
                escape = None
                if self.match(TokenType.ESCAPE):
                    escape = self._parse_expr_between()
                return BinaryOp('GLOB', left, right)
            elif self.peek() == TokenType.MATCH:
                right = self._parse_expr_between()
                return BinaryOp('MATCH', left, right)
            elif self.peek() == TokenType.REGEXP:
                right = self._parse_expr_between()
                return BinaryOp('REGEXP', left, right)
            break
        return left

    def _parse_in_op(self, left: Expr, negated: bool) -> InOp:
        self.advance()
        self.expect(TokenType.LPAREN)
        if self.peek() in (TokenType.SELECT, TokenType.WITH):
            select = self._parse_select()
            self.expect(TokenType.RPAREN)
            return InOp(left, select=select, negated=negated)
        values = []
        if self.peek() != TokenType.RPAREN:
            values.append(self._parse_expr())
            while self.match(TokenType.COMMA):
                values.append(self._parse_expr())
        self.expect(TokenType.RPAREN)
        return InOp(left, values=values, negated=negated)

    def _parse_like_op(self, left: Expr, negated: bool) -> LikeOp:
        self.advance()
        pattern = self._parse_expr_between()
        escape = None
        if self.match(TokenType.ESCAPE):
            escape = self._parse_expr_between()
        return LikeOp(left, pattern, escape=escape, negated=negated)

    def _parse_expr_between(self) -> Expr:
        left = self._parse_expr_concat()
        if self.match(TokenType.BETWEEN):
            low = self._parse_expr_concat()
            self.expect(TokenType.AND)
            high = self._parse_expr_concat()
            return BetweenOp(left, low, high, negated=False)
        if self.match(TokenType.NOT):
            if self.match(TokenType.BETWEEN):
                low = self._parse_expr_concat()
                self.expect(TokenType.AND)
                high = self._parse_expr_concat()
                return BetweenOp(left, low, high, negated=True)
            self.idx -= 1
        return left

    def _parse_expr_concat(self) -> Expr:
        left = self._parse_expr_comp()
        while self.match(TokenType.CONCAT):
            right = self._parse_expr_comp()
            left = BinaryOp('||', left, right)
        return left

    def _parse_expr_comp(self) -> Expr:
        left = self._parse_expr_shift()
        while self.peek() in (TokenType.LT, TokenType.LE, TokenType.GT, TokenType.GE,
                                TokenType.EQ, TokenType.EQ2, TokenType.NE, TokenType.NE2):
            op = self.advance().value
            right = self._parse_expr_shift()
            left = BinaryOp(op, left, right)
        return left

    def _parse_expr_shift(self) -> Expr:
        left = self._parse_expr_bit()
        while self.peek() in (TokenType.LSHIFT, TokenType.RSHIFT, TokenType.AMPERSAND,
                                TokenType.PIPE):
            op = self.advance().value
            right = self._parse_expr_bit()
            left = BinaryOp(op, left, right)
        return left

    def _parse_expr_bit(self) -> Expr:
        left = self._parse_expr_add()
        while self.peek() in (TokenType.PLUS, TokenType.MINUS):
            op = self.advance().value
            right = self._parse_expr_add()
            left = BinaryOp(op, left, right)
        return left

    def _parse_expr_add(self) -> Expr:
        left = self._parse_expr_mul()
        while self.peek() in (TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self.advance().value
            right = self._parse_expr_mul()
            left = BinaryOp(op, left, right)
        return left

    def _parse_expr_mul(self) -> Expr:
        return self._parse_expr_unary()

    def _parse_expr_unary(self) -> Expr:
        if self.peek() in (TokenType.PLUS, TokenType.MINUS, TokenType.TILDE):
            op = self.advance().value
            return UnaryOp(op, self._parse_expr_unary())
        return self._parse_expr_collate()

    def _parse_expr_collate(self) -> Expr:
        left = self._parse_primary()
        if self.match(TokenType.COLLATE):
            coll = self.expect(TokenType.IDENTIFIER).value
            left = CollateOp(left, coll)
        return left

    def _parse_primary(self) -> Expr:
        tt = self.peek()

        if tt == TokenType.LPAREN:
            self.advance()
            if self.peek() in (TokenType.SELECT, TokenType.WITH):
                select = self._parse_select()
                self.expect(TokenType.RPAREN)
                return Subquery(select)
            expr = self._parse_expr()
            self.expect(TokenType.RPAREN)
            return expr

        if tt == TokenType.EXISTS:
            self.advance()
            self.expect(TokenType.LPAREN)
            select = self._parse_select()
            self.expect(TokenType.RPAREN)
            return ExistsSubquery(select)

        if tt == TokenType.CASE:
            return self._parse_case()

        if tt == TokenType.CAST:
            return self._parse_cast()

        if tt == TokenType.RAISE:
            return self._parse_raise()

        if tt in (TokenType.INTEGER, TokenType.FLOAT, TokenType.STRING,
                   TokenType.BLOB, TokenType.NULL):
            return self._parse_literal()

        if tt == TokenType.IDENTIFIER:
            value = self.advance().value
            if self.match(TokenType.DOT):
                table = value
                col = self.expect(TokenType.IDENTIFIER).value
                if self.peek() == TokenType.LPAREN:
                    return FunctionCall(name=col, args=[ColumnRef(name=col, table=table)])
                return ColumnRef(name=col, table=table)
            if self.peek() == TokenType.LPAREN:
                return self._parse_function_call(value)
            if self.peek() == TokenType.DOT:
                col = self.advance()
                return ColumnRef(name=value)
            return ColumnRef(name=value)

        raise ParseError(f"Unexpected token in expression: {tt.name}")

    def _parse_literal(self) -> Literal:
        tt = self.peek()
        if tt == TokenType.NULL:
            self.advance()
            return NullLiteral()
        if tt == TokenType.INTEGER:
            return Literal(int(self.advance().value))
        if tt == TokenType.FLOAT:
            return Literal(float(self.advance().value))
        if tt == TokenType.STRING:
            val = self.advance().value
            if val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            return Literal(val)
        if tt == TokenType.BLOB:
            return Literal(self.advance().value)
        raise ParseError(f"Expected literal, got {tt.name}")

    def _parse_function_call(self, name: str) -> FunctionCall:
        self.expect(TokenType.LPAREN)
        distinct = self.match(TokenType.DISTINCT)
        star = False
        args = []
        if self.peek() != TokenType.RPAREN:
            if self.match(TokenType.STAR):
                star = True
            else:
                args.append(self._parse_expr())
                while self.match(TokenType.COMMA):
                    args.append(self._parse_expr())
        self.expect(TokenType.RPAREN)
        filter_clause = None
        if self.match(TokenType.FILTER):
            self.expect(TokenType.LPAREN)
            self.expect(TokenType.WHERE)
            filter_clause = self._parse_expr()
            self.expect(TokenType.RPAREN)
        over = None
        if self.match(TokenType.OVER):
            if self.peek() == TokenType.LPAREN:
                self.advance()
                over = self._parse_window_spec()
                self.expect(TokenType.RPAREN)
            else:
                over = WindowDef(name=self.expect(TokenType.IDENTIFIER).value)
        return FunctionCall(name=name, args=args, distinct=distinct, star=star,
                            filter_clause=filter_clause, over=over)

    def _parse_case(self) -> CaseExpr:
        self.advance()
        base = None
        if self.peek() not in (TokenType.WHEN, TokenType.ELSE, TokenType.END):
            base = self._parse_expr()
        whens = []
        while self.match(TokenType.WHEN):
            cond = self._parse_expr()
            self.expect(TokenType.THEN)
            val = self._parse_expr()
            whens.append((cond, val))
        else_expr = None
        if self.match(TokenType.ELSE):
            else_expr = self._parse_expr()
        self.expect(TokenType.END)
        return CaseExpr(base=base, whens=whens, else_expr=else_expr)

    def _parse_cast(self) -> CastExpr:
        self.advance()
        self.expect(TokenType.LPAREN)
        expr = self._parse_expr()
        self.expect(TokenType.AS)
        type_name = self._parse_type_name()
        self.expect(TokenType.RPAREN)
        return CastExpr(expr=expr, type_name=type_name)

    def _parse_raise(self) -> RaiseFunction:
        self.advance()
        self.expect(TokenType.LPAREN)
        if self.match(TokenType.IGNORE):
            self.expect(TokenType.RPAREN)
            return RaiseFunction(action='IGNORE')
        action = self.expect_any(TokenType.ROLLBACK, TokenType.ABORT, TokenType.FAIL).value
        self.expect(TokenType.COMMA)
        msg = self.expect(TokenType.STRING).value
        self.expect(TokenType.RPAREN)
        return RaiseFunction(action=action.upper(), error_msg=msg)

    def _parse_ordering_term(self) -> OrderingTerm:
        expr = self._parse_expr()
        direction = 'ASC'
        if self.match(TokenType.ASC):
            direction = 'ASC'
        elif self.match(TokenType.DESC):
            direction = 'DESC'
        nulls = None
        if self.match(TokenType.NULLS):
            if self.match(TokenType.FIRST):
                nulls = 'FIRST'
            elif self.match(TokenType.LAST):
                nulls = 'LAST'
        return OrderingTerm(expr=expr, direction=direction, nulls=nulls)
