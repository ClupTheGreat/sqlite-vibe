"""FTS5 virtual table module — full-text search."""

import re
import math
from collections import defaultdict

from pysqlite.virtualtables import VirtualTable, register_module


# ── Tokenizers ──

class Unicode61Tokenizer:
    def tokenize(self, text: str) -> list[str]:
        tokens = re.findall(r"[^\W_]+", text.lower())
        return tokens


class AsciiTokenizer:
    def tokenize(self, text: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z]+", text.lower())
        return tokens


class TrigramTokenizer:
    def tokenize(self, text: str) -> list[str]:
        clean = re.sub(r'\s+', ' ', text.lower()).strip()
        if len(clean) < 3:
            return [clean] if clean else []
        return [clean[i:i+3] for i in range(len(clean) - 2)]


_TOKENIZERS = {
    'unicode61': Unicode61Tokenizer,
    'ascii': AsciiTokenizer,
    'trigram': TrigramTokenizer,
}


# ── Match query parser ──

class MatchQuery:
    """Parses and evaluates FTS5 MATCH queries."""

    def __init__(self, query: str):
        self._original = query
        self._tokens = self._tokenize_query(query)

    @staticmethod
    def _tokenize_query(query: str) -> list:
        """Tokenize a MATCH query string into terms, operators, and phrases."""
        tokens = []
        i = 0
        while i < len(query):
            if query[i] in ' \t\n\r':
                i += 1
                continue
            if query[i] == '"':
                j = query.index('"', i + 1) if '"' in query[i+1:] else len(query)
                phrase = query[i+1:j]
                tokens.append(('PHRASE', phrase.lower()))
                i = j + 1
            else:
                word_match = re.match(r'([a-zA-Z0-9_*^]+)', query[i:])
                if word_match:
                    word = word_match.group(1)
                    if word.upper() in ('AND', 'OR', 'NOT'):
                        tokens.append(('OP', word.upper()))
                    elif word.startswith('^'):
                        tokens.append(('PREFIX_ANCHOR', word[1:].lower()))
                    elif word.endswith('*'):
                        tokens.append(('PREFIX', word[:-1].lower()))
                    elif ':' in word:
                        col, _, term = word.partition(':')
                        tokens.append(('COLUMN', col.lower(), term.lower()))
                    else:
                        tokens.append(('TERM', word.lower()))
                    i += word_match.end()
                else:
                    i += 1
        return tokens

    def evaluate(self, inverted_index: dict, doc_count: int,
                 doc_lengths: dict) -> set:
        """Evaluate the query against an inverted index.
        Returns set of matching docids.
        """
        if not self._tokens:
            return set()

        result = None
        i = 0
        while i < len(self._tokens):
            tok = self._tokens[i]
            if tok[0] == 'OP':
                i += 1
                continue

            negate = False
            if tok[0] == 'OP' and tok[1] == 'NOT':
                negate = True
                i += 1
                tok = self._tokens[i]

            docs = self._eval_single(tok, inverted_index)

            if negate:
                all_docs = set(range(1, doc_count + 1))
                docs = all_docs - docs

            if result is None:
                result = docs
            else:
                prev_op = None
                for j in range(i - 2, -1, -1):
                    if self._tokens[j][0] == 'OP':
                        prev_op = self._tokens[j][1]
                        break
                if prev_op == 'OR':
                    result = result | docs
                else:
                    result = result & docs
            i += 1

        return result or set()

    def _eval_single(self, tok: tuple, inverted_index: dict) -> set:
        typ = tok[0]
        if typ == 'TERM':
            term = tok[1]
            return {docid for (docid, _) in inverted_index.get(term, set())}
        elif typ == 'PHRASE':
            phrase = tok[1]
            words = phrase.split()
            if not words:
                return set()
            if len(words) == 1:
                return {docid for (docid, _) in inverted_index.get(words[0], set())}
            matches = None
            for word in words:
                docs = {docid for (docid, _) in inverted_index.get(word, set())}
                if matches is None:
                    matches = docs
                else:
                    matches &= docs
            return matches or set()
        elif typ == 'PREFIX':
            prefix = tok[1]
            result = set()
            for term, docs in inverted_index.items():
                if term.startswith(prefix):
                    result |= {docid for (docid, _) in docs}
            return result
        elif typ == 'COLUMN':
            _, col_name, term = tok
            matching = set()
            for (docid, col_idx), _ in inverted_index.get(term, set()):
                matching.add(docid)
            return matching
        return set()


# ── FTS5Table ──

class FTS5Table(VirtualTable):
    def __init__(self, name: str, args: list[str], config: dict | None = None):
        self.name = name
        self.args = args
        self.tokenizer_name = 'unicode61'
        self.content_table = f'{name}_content'
        self._parse_args(args)
        tokenizer_cls = _TOKENIZERS.get(self.tokenizer_name, Unicode61Tokenizer)
        self._tokenizer = tokenizer_cls()
        self._inverted_index: dict[str, set[tuple[int, int]]] = defaultdict(set)
        self._doc_lengths: dict[int, int] = {}
        self._next_docid = 1
        self._config = config or {}

    def _parse_args(self, args: list[str]):
        cols = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg.startswith('tokenize='):
                self.tokenizer_name = arg[len('tokenize='):]
                i += 1
            elif '=' in arg:
                i += 1
            else:
                cols.append(arg)
                i += 1
        self._columns = cols

    def all_columns(self) -> list[str]:
        return ['docid'] + self._columns

    @property
    def columns(self) -> list[str]:
        return self._columns

    def insert(self, docid: int, values: list[str | None]):
        for col_idx, val in enumerate(values):
            if val and col_idx < len(self._columns):
                tokens = self._tokenizer.tokenize(str(val))
                self._doc_lengths[docid] = self._doc_lengths.get(docid, 0) + len(tokens)
                for token in tokens:
                    self._inverted_index[token].add((docid, col_idx))

    def delete(self, docid: int, ncols: int):
        self._doc_lengths.pop(docid, None)
        keys_to_remove = []
        for term, docs in self._inverted_index.items():
            docs.difference_update({(docid, ci) for ci in range(ncols)})
            if not docs:
                keys_to_remove.append(term)
        for k in keys_to_remove:
            del self._inverted_index[k]

    def update(self, docid: int, old_values: list[str | None],
               new_values: list[str | None]):
        self.delete(docid, len(old_values))
        self.insert(docid, new_values)

    def match(self, query: str) -> set[int]:
        mq = MatchQuery(query)
        doc_count = (self._next_docid - 1) if hasattr(self, '_next_docid') else 0
        return mq.evaluate(dict(self._inverted_index), doc_count, self._doc_lengths)

    def bm25_score(self, docid: int, query: str) -> float:
        matching = self.match(query)
        if docid not in matching:
            return 0.0
        k1 = 1.2
        b = 0.75
        avgdl = 1.0
        if self._doc_lengths:
            avgdl = sum(self._doc_lengths.values()) / len(self._doc_lengths)
        N = len(matching)
        score = 0.0
        mq = MatchQuery(query)
        for tok in mq._tokens:
            if tok[0] != 'TERM':
                continue
            term = tok[1]
            docs_with_term = len(self._inverted_index.get(term, set()))
            if docs_with_term == 0:
                continue
            idf = math.log((N - docs_with_term + 0.5) / (docs_with_term + 0.5) + 1.0)
            dl = self._doc_lengths.get(docid, 1)
            tf = sum(1 for (d, _) in self._inverted_index.get(term, set()) if d == docid)
            if tf == 0:
                continue
            tf_norm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))
            score += idf * tf_norm
        return score

    def close(self):
        self._inverted_index.clear()
        self._doc_lengths.clear()


register_module('fts5', FTS5Table)
