"""SQL tokenizer — breaks SQL text into tokens."""

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    # Keywords
    CREATE = auto(); DROP = auto(); ALTER = auto(); TABLE = auto()
    INDEX = auto(); VIEW = auto(); TRIGGER = auto(); VIRTUAL = auto()
    SELECT = auto(); INSERT = auto(); UPDATE = auto(); DELETE = auto()
    INTO = auto(); FROM = auto(); WHERE = auto(); SET = auto()
    VALUES = auto(); DEFAULT = auto(); JOIN = auto(); LEFT = auto()
    RIGHT = auto(); INNER = auto(); OUTER = auto(); CROSS = auto()
    NATURAL = auto(); ON = auto(); USING = auto(); AS = auto()
    AND = auto(); OR = auto(); NOT = auto(); NULL = auto(); IS = auto()
    IN = auto(); BETWEEN = auto(); LIKE = auto(); GLOB = auto()
    MATCH = auto(); REGEXP = auto(); ESCAPE = auto()
    EXISTS = auto(); CASE = auto(); WHEN = auto(); THEN = auto()
    ELSE = auto(); END = auto(); CAST = auto()
    GROUP = auto(); BY = auto(); HAVING = auto(); ORDER = auto()
    ASC = auto(); DESC = auto(); LIMIT = auto(); OFFSET = auto()
    DISTINCT = auto(); ALL = auto(); UNION = auto(); INTERSECT = auto()
    EXCEPT = auto(); FOR = auto(); RETURNING = auto()
    PRIMARY = auto(); KEY = auto(); UNIQUE = auto(); CHECK = auto()
    REFERENCES = auto(); FOREIGN = auto(); CONSTRAINT = auto()
    AUTOINCREMENT = auto(); COLLATE = auto(); GENERATED = auto()
    ALWAYS = auto(); STORED = auto(); VIRTUAL_KW = auto()
    WITHOUT = auto(); ROWID = auto(); STRICT = auto(); TEMP = auto()
    TEMPORARY = auto(); IF = auto(); RAISE = auto(); IGNORE = auto()
    ABORT = auto(); FAIL = auto(); REPLACE = auto(); ROLLBACK = auto()
    CONFLICT = auto(); DO = auto(); NOTHING = auto(); CASCADE = auto()
    RESTRICT = auto();     SET_NULL = auto(); SET_DEFAULT = auto()
    DEFERRED = auto(); IMMEDIATE = auto(); EXCLUSIVE = auto()
    BEGIN = auto(); COMMIT = auto(); ROLLBACK_STMT = auto()
    SAVEPOINT = auto(); RELEASE = auto(); TO = auto(); OF = auto()
    ADD = auto(); COLUMN = auto(); TRANSACTION = auto(); NULLS = auto()
    RENAME = auto(); BEFORE = auto(); AFTER = auto(); INSTEAD = auto()
    FIRST = auto(); LAST = auto()
    PRAGMA = auto(); ANALYZE = auto(); REINDEX = auto(); VACUUM = auto()
    EXPLAIN = auto(); QUERY = auto(); PLAN = auto(); WITH = auto()
    RECURSIVE = auto(); WINDOW = auto(); FILTER = auto(); OVER = auto()
    PARTITION = auto(); ROWS = auto(); RANGE = auto(); GROUPS = auto()
    UNBOUNDED = auto(); PRECEDING = auto(); FOLLOWING = auto()
    CURRENT_ROW = auto(); EXCLUDE = auto(); TIES = auto()
    # Literals
    IDENTIFIER = auto(); QUOTED_ID = auto(); BACKTICK_ID = auto()
    BRACKET_ID = auto(); INTEGER = auto(); FLOAT = auto(); STRING = auto()
    BLOB = auto()
    # Operators
    PLUS = auto(); MINUS = auto(); STAR = auto(); SLASH = auto()
    PERCENT = auto(); AMPERSAND = auto(); PIPE = auto(); TILDE = auto()
    LT = auto(); GT = auto(); LE = auto(); GE = auto(); EQ = auto()
    EQ2 = auto(); NE = auto(); NE2 = auto(); CONCAT = auto()
    LSHIFT = auto(); RSHIFT = auto(); ARROW = auto(); ARROW2 = auto()
    # Punctuation
    LPAREN = auto(); RPAREN = auto(); LBRACKET = auto(); RBRACKET = auto()
    DOT = auto(); COMMA = auto(); SEMI = auto()
    # Special
    EOF = auto()


_KEYWORDS = {
    'CREATE': TokenType.CREATE, 'DROP': TokenType.DROP,
    'ALTER': TokenType.ALTER, 'TABLE': TokenType.TABLE,
    'INDEX': TokenType.INDEX, 'VIEW': TokenType.VIEW,
    'TRIGGER': TokenType.TRIGGER, 'VIRTUAL': TokenType.VIRTUAL,
    'SELECT': TokenType.SELECT, 'INSERT': TokenType.INSERT,
    'UPDATE': TokenType.UPDATE, 'DELETE': TokenType.DELETE,
    'INTO': TokenType.INTO, 'FROM': TokenType.FROM,
    'WHERE': TokenType.WHERE, 'SET': TokenType.SET,
    'VALUES': TokenType.VALUES, 'DEFAULT': TokenType.DEFAULT,
    'JOIN': TokenType.JOIN, 'LEFT': TokenType.LEFT,
    'RIGHT': TokenType.RIGHT, 'INNER': TokenType.INNER,
    'OUTER': TokenType.OUTER, 'CROSS': TokenType.CROSS,
    'NATURAL': TokenType.NATURAL, 'ON': TokenType.ON,
    'USING': TokenType.USING, 'AS': TokenType.AS,
    'AND': TokenType.AND, 'OR': TokenType.OR, 'NOT': TokenType.NOT,
    'NULL': TokenType.NULL, 'IS': TokenType.IS, 'IN': TokenType.IN,
    'BETWEEN': TokenType.BETWEEN, 'LIKE': TokenType.LIKE,
    'GLOB': TokenType.GLOB, 'MATCH': TokenType.MATCH,
    'REGEXP': TokenType.REGEXP, 'ESCAPE': TokenType.ESCAPE,
    'EXISTS': TokenType.EXISTS, 'CASE': TokenType.CASE,
    'WHEN': TokenType.WHEN, 'THEN': TokenType.THEN,
    'ELSE': TokenType.ELSE, 'END': TokenType.END,
    'CAST': TokenType.CAST,
    'GROUP': TokenType.GROUP, 'BY': TokenType.BY,
    'HAVING': TokenType.HAVING, 'ORDER': TokenType.ORDER,
    'ASC': TokenType.ASC, 'DESC': TokenType.DESC,
    'LIMIT': TokenType.LIMIT, 'OFFSET': TokenType.OFFSET,
    'DISTINCT': TokenType.DISTINCT, 'ALL': TokenType.ALL,
    'UNION': TokenType.UNION, 'INTERSECT': TokenType.INTERSECT,
    'EXCEPT': TokenType.EXCEPT, 'FOR': TokenType.FOR,
    'RETURNING': TokenType.RETURNING,
    'PRIMARY': TokenType.PRIMARY, 'KEY': TokenType.KEY,
    'UNIQUE': TokenType.UNIQUE, 'CHECK': TokenType.CHECK,
    'REFERENCES': TokenType.REFERENCES, 'FOREIGN': TokenType.FOREIGN,
    'CONSTRAINT': TokenType.CONSTRAINT,
    'AUTOINCREMENT': TokenType.AUTOINCREMENT,
    'COLLATE': TokenType.COLLATE, 'GENERATED': TokenType.GENERATED,
    'ALWAYS': TokenType.ALWAYS, 'STORED': TokenType.STORED,
    'VIRTUAL': TokenType.VIRTUAL_KW,
    'WITHOUT': TokenType.WITHOUT, 'ROWID': TokenType.ROWID,
    'STRICT': TokenType.STRICT, 'TEMP': TokenType.TEMP,
    'TEMPORARY': TokenType.TEMPORARY, 'IF': TokenType.IF,
    'RAISE': TokenType.RAISE, 'IGNORE': TokenType.IGNORE,
    'ABORT': TokenType.ABORT, 'FAIL': TokenType.FAIL,
    'REPLACE': TokenType.REPLACE, 'ROLLBACK': TokenType.ROLLBACK,
    'CONFLICT': TokenType.CONFLICT, 'DO': TokenType.DO,
    'NOTHING': TokenType.NOTHING, 'CASCADE': TokenType.CASCADE,
    'RESTRICT': TokenType.RESTRICT,
    'ADD': TokenType.ADD, 'COLUMN': TokenType.COLUMN,
    'TRANSACTION': TokenType.TRANSACTION, 'NULLS': TokenType.NULLS,
    'RENAME': TokenType.RENAME, 'BEFORE': TokenType.BEFORE,
    'AFTER': TokenType.AFTER, 'INSTEAD': TokenType.INSTEAD,
    'FIRST': TokenType.FIRST, 'LAST': TokenType.LAST,
    'DEFERRED': TokenType.DEFERRED, 'IMMEDIATE': TokenType.IMMEDIATE,
    'EXCLUSIVE': TokenType.EXCLUSIVE,
    'BEGIN': TokenType.BEGIN, 'COMMIT': TokenType.COMMIT,
    'SAVEPOINT': TokenType.SAVEPOINT, 'RELEASE': TokenType.RELEASE,
    'TO': TokenType.TO, 'OF': TokenType.OF,
    'PRAGMA': TokenType.PRAGMA, 'ANALYZE': TokenType.ANALYZE,
    'REINDEX': TokenType.REINDEX, 'VACUUM': TokenType.VACUUM,
    'EXPLAIN': TokenType.EXPLAIN, 'QUERY': TokenType.QUERY,
    'PLAN': TokenType.PLAN, 'WITH': TokenType.WITH,
    'RECURSIVE': TokenType.RECURSIVE, 'WINDOW': TokenType.WINDOW,
    'FILTER': TokenType.FILTER, 'OVER': TokenType.OVER,
    'PARTITION': TokenType.PARTITION,
    'ROWS': TokenType.ROWS, 'RANGE': TokenType.RANGE,
    'GROUPS': TokenType.GROUPS, 'UNBOUNDED': TokenType.UNBOUNDED,
    'PRECEDING': TokenType.PRECEDING, 'FOLLOWING': TokenType.FOLLOWING,
    'CURRENT_ROW': TokenType.CURRENT_ROW, 'EXCLUDE': TokenType.EXCLUDE,
    'TIES': TokenType.TIES,
}


@dataclass
class Token:
    type: TokenType
    value: str
    start: int = 0
    end: int = 0
    line: int = 1
    col: int = 1

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r})"


_OP_TABLE: dict[str, TokenType] = {
    '+': TokenType.PLUS, '-': TokenType.MINUS, '*': TokenType.STAR,
    '/': TokenType.SLASH, '%': TokenType.PERCENT,
    '&': TokenType.AMPERSAND, '|': TokenType.PIPE, '~': TokenType.TILDE,
    '<': TokenType.LT, '>': TokenType.GT,
    '<=': TokenType.LE, '>=': TokenType.GE,
    '=': TokenType.EQ, '==': TokenType.EQ2,
    '<>': TokenType.NE, '!=': TokenType.NE2,
    '||': TokenType.CONCAT, '<<': TokenType.LSHIFT, '>>': TokenType.RSHIFT,
    '->': TokenType.ARROW, '->>': TokenType.ARROW2,
}

_MULTI_CHAR_OPS = {'<=', '>=', '==', '<>', '!=', '||', '<<', '>>', '->>', '->'}


class LexerError(Exception):
    pass


class Lexer:
    def __init__(self, sql: str):
        self.sql = sql
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: list[Token] = []
        self._tok_line = 1
        self._tok_col = 1

    def tokenize(self) -> list[Token]:
        self.tokens = []
        while self.pos < len(self.sql):
            ch = self.sql[self.pos]
            start = self.pos
            line, col = self.line, self.col

            self._tok_line, self._tok_col = line, col
            if ch in ' \t\r\n':
                self._advance()
                if ch == '\n':
                    self.line += 1
                    self.col = 1
                continue

            if ch == '-' and self._peek() == '-':
                self._skip_line_comment()
                continue

            if ch == '/' and self._peek() == '*':
                self._skip_block_comment()
                continue

            if ch == ';':
                self._advance()
                self._emit(TokenType.SEMI, ';', start)
                continue

            if ch in '(),.':
                self._advance()
                tt = {',': TokenType.COMMA, '.': TokenType.DOT,
                      '(': TokenType.LPAREN, ')': TokenType.RPAREN}[ch]
                self._emit(tt, ch, start)
                continue

            if ch == '[':
                self._read_bracket_id()
                continue

            if ch == '`':
                self._read_backtick_id()
                continue

            if ch == "'":
                self._read_string()
                continue

            if ch == '"':
                self._read_quoted_id()
                continue

            if ch == 'x' or ch == 'X':
                if self._peek() == "'":
                    self._read_blob(start)
                    continue

            if ch.isdigit() or (ch == '.' and self._peek() and self._peek().isdigit()):
                self._read_number(start)
                continue

            if ch.isalpha() or ch == '_':
                self._read_ident_or_keyword(start)
                continue

            if ch in '+-*/%&|~<>=!':
                self._read_operator(start)
                continue

            raise LexerError(f"Unexpected character {ch!r} at {line}:{col}")

        self.tokens.append(Token(TokenType.EOF, '', self.pos, self.pos, self.line, self.col))
        return self.tokens

    def _advance(self) -> str:
        ch = self.sql[self.pos]
        self.pos += 1
        self.col += 1
        return ch

    def _peek(self, n: int = 0) -> str | None:
        idx = self.pos + 1 + n
        return self.sql[idx] if idx < len(self.sql) else None

    def _emit(self, tt: TokenType, value: str, start: int,
              line: int | None = None, col: int | None = None):
        self.tokens.append(Token(tt, value, start, self.pos,
                                 line if line is not None else self._tok_line,
                                 col if col is not None else self._tok_col))

    def _skip_line_comment(self):
        while self.pos < len(self.sql) and self.sql[self.pos] != '\n':
            self._advance()

    def _skip_block_comment(self):
        self._advance()
        self._advance()
        while self.pos < len(self.sql):
            if self.sql[self.pos] == '*' and self._peek() == '/':
                self._advance()
                self._advance()
                return
            if self.sql[self.pos] == '\n':
                self.line += 1
                self.col = 1
            self._advance()

    def _read_ident_or_keyword(self, start: int):
        while self.pos < len(self.sql):
            ch = self.sql[self.pos]
            if ch.isalnum() or ch == '_':
                self._advance()
            else:
                break
        word = self.sql[start:self.pos]
        upper = word.upper()
        tt = _KEYWORDS.get(upper, TokenType.IDENTIFIER)
        self._emit(tt, word, start)

    def _read_number(self, start: int):
        is_float = self.sql[start] == '.'
        while self.pos < len(self.sql):
            ch = self.sql[self.pos]
            if ch.isdigit():
                self._advance()
            elif ch == '.' and not is_float:
                is_float = True
                self._advance()
            elif ch in 'eE':
                is_float = True
                self._advance()
                if self.pos < len(self.sql) and self.sql[self.pos] in '+-':
                    self._advance()
            else:
                break
        value = self.sql[start:self.pos]
        tt = TokenType.FLOAT if is_float else TokenType.INTEGER
        self._emit(tt, value, start)

    def _read_string(self):
        start = self.pos
        delim = self._advance()
        while self.pos < len(self.sql):
            ch = self._advance()
            if ch == delim:
                if self.pos < len(self.sql) and self.sql[self.pos] == delim:
                    self._advance()
                else:
                    break
        self._emit(TokenType.STRING, self.sql[start:self.pos], start)

    def _read_quoted_id(self):
        start = self.pos
        delim = self._advance()
        while self.pos < len(self.sql):
            ch = self._advance()
            if ch == delim:
                if self.pos < len(self.sql) and self.sql[self.pos] == delim:
                    self._advance()
                else:
                    break
        self._emit(TokenType.QUOTED_ID, self.sql[start:self.pos], start)

    def _read_bracket_id(self):
        start = self.pos
        self._advance()
        while self.pos < len(self.sql) and self.sql[self.pos] != ']':
            self._advance()
        self._advance()
        self._emit(TokenType.BRACKET_ID, self.sql[start:self.pos], start)

    def _read_backtick_id(self):
        start = self.pos
        self._advance()
        while self.pos < len(self.sql) and self.sql[self.pos] != '`':
            self._advance()
        self._advance()
        self._emit(TokenType.BACKTICK_ID, self.sql[start:self.pos], start)

    def _read_blob(self, start: int):
        self._advance()
        self._advance()
        while self.pos < len(self.sql) and self.sql[self.pos] != "'":
            self._advance()
        self._advance()
        self._emit(TokenType.BLOB, self.sql[start:self.pos], start)

    def _read_operator(self, start: int):
        three = self.sql[start:start + 3] if start + 3 <= len(self.sql) else ''
        if three in _MULTI_CHAR_OPS:
            for _ in range(3):
                self._advance()
            self._emit(_OP_TABLE[three], three, start)
            return
        two = self.sql[start:start + 2] if start + 2 <= len(self.sql) else ''
        if two in _MULTI_CHAR_OPS:
            self._advance()
            self._advance()
            self._emit(_OP_TABLE[two], two, start)
        else:
            self._advance()
            self._emit(_OP_TABLE[self.sql[start]], self.sql[start], start)
