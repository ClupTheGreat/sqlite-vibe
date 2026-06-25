"""Fuzz tests — random SQL, corrupted database files."""

import random
import string
import tempfile
import os
import pytest
from pysqlite import Database
from pysqlite.errors import DatabaseError


def _random_string(max_len=20):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(0, max_len)))


def _random_value():
    return random.choice([
        random.randint(-1000, 1000),
        _random_string(10),
        float(random.randint(-100, 100)),
        None,
    ])


class TestRandomSQL:
    def test_random_sql_mutations(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t1 (a INT, b TEXT, c REAL)')
        db.execute('CREATE TABLE t2 (x INT, y TEXT)')
        for i in range(50):
            db.execute(f'INSERT INTO t1 VALUES ({i}, \'v{i}\', {float(i)})')
        for i in range(10):
            db.execute(f'INSERT INTO t2 VALUES ({i}, \'str{i}\')')

        templates = [
            'SELECT * FROM t1 WHERE a {op} {val}',
            'SELECT * FROM t1 WHERE b {op} {val}',
            'SELECT * FROM t1 ORDER BY a',
            'SELECT * FROM t1 ORDER BY b DESC',
            'SELECT * FROM t1 WHERE a BETWEEN {lo} AND {hi}',
            'SELECT * FROM t1 WHERE a IS NULL',
            'SELECT * FROM t1 WHERE a IS NOT NULL',
            'SELECT count(*) FROM t1',
            'SELECT sum(a) FROM t1',
            'SELECT a, count(*) FROM t1 GROUP BY a',
            'INSERT INTO t1 VALUES ({v1}, {v2}, {v3})',
            'UPDATE t1 SET b = {v} WHERE a = {k}',
            'DELETE FROM t1 WHERE a = {k}',
        ]

        for _ in range(200):
            tmpl = random.choice(templates)
            sql = tmpl.format(
                op=random.choice(['=', '<', '>', '<=', '>=', '<>', '!=', 'LIKE']),
                val=repr(_random_value()),
                lo=random.randint(0, 20),
                hi=random.randint(21, 50),
                v1=random.randint(1, 1000),
                v2=repr(_random_string()),
                v3=float(random.randint(1, 100)),
                v=repr(_random_string()),
                k=random.randint(0, 49),
            )
            try:
                db.execute(sql)
            except (DatabaseError, Exception):
                pass

        db.close()


class TestCorruptDb:
    def test_truncated_header(self):
        import tempfile
        path = tempfile.mktemp(suffix='.db')
        with open(path, 'wb') as f:
            f.write(b'\x00' * 50)
        try:
            with pytest.raises(Exception):
                db = Database(path)
                db.close()
        finally:
            try:
                os.unlink(path)
            except PermissionError:
                pass

    def test_invalid_page_size(self):
        import tempfile
        path = tempfile.mktemp(suffix='.db')
        header = bytearray(100)
        header[0:16] = b'SQLite format 3\x00'
        header[16:18] = (7).to_bytes(2, 'big')
        with open(path, 'wb') as f:
            f.write(bytes(header))
        try:
            with pytest.raises(Exception):
                db = Database(path)
                db.close()
        finally:
            try:
                os.unlink(path)
            except PermissionError:
                pass

    def test_random_bytes_as_db(self):
        import tempfile
        path = tempfile.mktemp(suffix='.db')
        with open(path, 'wb') as f:
            f.write(bytes(random.randint(0, 255) for _ in range(200)))
        try:
            with pytest.raises(Exception):
                db = Database(path)
                db.close()
        finally:
            try:
                os.unlink(path)
            except PermissionError:
                pass
