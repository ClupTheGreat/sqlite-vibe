"""Tests for record encoding/decoding."""

import math
import pytest
from pysqlite.record import Record


class TestSerialType:
    def test_null(self):
        assert Record.serial_type(None) == 0

    def test_bool(self):
        assert Record.serial_type(True) == 1
        assert Record.serial_type(False) == 0  # bool(False) is 0, serial type 8

    def test_int_zero_one(self):
        assert Record.serial_type(0) == 8
        assert Record.serial_type(1) == 9

    def test_int_ranges(self):
        assert Record.serial_type(127) == 1
        assert Record.serial_type(-128) == 1
        assert Record.serial_type(128) == 2
        assert Record.serial_type(-32768) == 2
        assert Record.serial_type(32768) == 3
        assert Record.serial_type(2**31 - 1) == 4
        assert Record.serial_type(-2**31) == 4
        assert Record.serial_type(2**47 - 1) == 5
        assert Record.serial_type(2**63 - 1) == 6

    def test_float(self):
        assert Record.serial_type(3.14) == 7

    def test_bytes(self):
        assert Record.serial_type(b'abc') == 12 + 6  # 3 bytes -> (12 + 2*3)

    def test_text(self):
        assert Record.serial_type('hello') == 13 + 10  # 5 chars = 5 utf8 bytes -> 13 + 2*5


class TestRoundtrip:
    def test_null(self):
        r = Record([(0, None)])
        data = r.encode()
        r2, _ = Record.decode(data)
        assert r2.get_values() == [None]

    def test_integers(self):
        vals = [(1, 42), (2, -32768), (4, 2**31 - 1), (6, 2**62), (8, 0), (9, 1)]
        r = Record(vals)
        data = r.encode()
        r2, _ = Record.decode(data)
        assert r2.get_values() == [42, -32768, 2**31 - 1, 2**62, 0, 1]

    def test_float(self):
        r = Record([(7, 3.141592653589793)])
        data = r.encode()
        r2, _ = Record.decode(data)
        assert r2.get_values()[0] == 3.141592653589793

    def test_text_ascii(self):
        r = Record([(13 + 10, 'hello')])
        data = r.encode()
        r2, _ = Record.decode(data)
        assert r2.get_values()[0] == 'hello'

    def test_text_unicode(self):
        # 'héllo' is 5 chars, é is 2 bytes in UTF-8 => 6 bytes total
        # serial_type = 13 + 2*6 = 25
        r = Record([(13 + 12, 'héllo')])
        data = r.encode()
        r2, _ = Record.decode(data)
        assert r2.get_values()[0] == 'héllo'

    def test_blob(self):
        r = Record([(12 + 6, b'\x00\x01\x02')])
        data = r.encode()
        r2, _ = Record.decode(data)
        assert r2.get_values()[0] == b'\x00\x01\x02'

    def test_mixed_columns(self):
        cols = [(0, None), (1, -1), (7, 1.5), (13 + 4, 'ab'), (12 + 2, b'\xff')]
        r = Record(cols)
        data = r.encode()
        r2, _ = Record.decode(data)
        v = r2.get_values()
        assert v[0] is None
        assert v[1] == -1
        assert v[2] == 1.5
        assert v[3] == 'ab'
        assert v[4] == b'\xff'


class TestEncodeDecode:
    def test_auto_serial_type(self):
        """Test using auto-determined serial types from Python values."""
        r = Record([(Record.serial_type(v), v) for v in [None, 42, 3.14, 'hi', b'\x00']])
        data = r.encode()
        r2, consumed = Record.decode(data)
        assert r2.get_values() == [None, 42, 3.14, 'hi', b'\x00']
        assert consumed == len(data)

    def test_empty_record(self):
        r = Record([])
        data = r.encode()
        r2, _ = Record.decode(data)
        assert r2.get_values() == []

    def test_negative_twos_complement(self):
        r = Record([(3, -1), (5, -2**40)])
        data = r.encode()
        r2, _ = Record.decode(data)
        vs = r2.get_values()
        assert vs[0] == -1
        assert vs[1] == -2**40

    def test_large_blob(self):
        blob = bytes(range(256))
        st = 12 + 2 * len(blob)
        r = Record([(st, blob)])
        data = r.encode()
        r2, _ = Record.decode(data)
        assert r2.get_values()[0] == blob
