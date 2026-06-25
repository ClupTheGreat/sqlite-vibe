"""Stress tests — large data volumes, long transactions."""

import pytest
from pysqlite import Database


class TestLargeInsert:
    def test_bulk_insert(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT, b TEXT, c REAL)')
        db.execute('BEGIN')
        n = 100
        for i in range(n):
            db.execute(f'INSERT INTO t VALUES ({i}, \'row{i}\', {float(i)})')
        db.execute('COMMIT')
        res = db.execute('SELECT count(*) FROM t')
        assert res[0][0] == n
        db.close()

    def test_bulk_insert_select(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT, b TEXT)')
        db.execute('BEGIN')
        n = 100
        for i in range(n):
            db.execute(f'INSERT INTO t VALUES ({i}, \'row{i}\')')
        db.execute('COMMIT')
        res = db.execute('SELECT count(*) FROM t WHERE a >= 50')
        assert res[0][0] == 50
        db.close()


class TestLargeTransactionRollback:
    def test_rollback_inserts(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (a INT)')
        db.execute('BEGIN')
        for i in range(10):
            db.execute(f'INSERT INTO t VALUES ({i})')
        db.execute('ROLLBACK')
        res = db.execute('SELECT * FROM t')
        assert res == []
        db.close()


class TestManyTables:
    def test_many_tables_and_indexes(self):
        db = Database(':memory:')
        for i in range(3):
            db.execute(f'CREATE TABLE t{i} (a INT, b TEXT)')
            db.execute(f'CREATE INDEX idx_t{i}_a ON t{i}(a)')
            db.execute('BEGIN')
            for j in range(20):
                db.execute(f'INSERT INTO t{i} VALUES ({j}, \'val{j}\')')
            db.execute('COMMIT')
        for i in range(3):
            res = db.execute(f'SELECT count(*) FROM t{i}')
            assert res[0][0] == 20
        db.close()


class TestLargeBlob:
    def test_large_blob_roundtrip(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (id INT, data BLOB)')
        blob = b'x' * 5000
        db.execute_params('INSERT INTO t VALUES (1, ?)', {'?1': blob})
        res = db.execute('SELECT data FROM t WHERE id = 1')
        assert res[0][0] == blob
        db.close()

    def test_small_blob_roundtrip(self):
        db = Database(':memory:')
        db.execute('CREATE TABLE t (id INT, data BLOB)')
        blob = b'\x01\x02\x03\xfe\xff'
        db.execute_params(f'INSERT INTO t VALUES (1, ?)', {'?1': blob})
        res = db.execute('SELECT * FROM t')
        assert len(res) == 1
        assert res[0][1] == blob
        db.close()


class TestManyColumns:
    def test_wide_table_select(self):
        db = Database(':memory:')
        cols = ', '.join(f'c{i} INT' for i in range(50))
        vals = ', '.join(str(i) for i in range(50))
        db.execute(f'CREATE TABLE t ({cols})')
        db.execute(f'INSERT INTO t VALUES ({vals})')
        res = db.execute('SELECT * FROM t')
        assert len(res[0]) == 50
        assert res[0][49] == 49
        db.close()
