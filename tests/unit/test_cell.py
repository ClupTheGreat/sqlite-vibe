"""Tests for cell serialization."""

from pysqlite.cell import (
    TableLeafCell, TableInteriorCell, IndexLeafCell, IndexInteriorCell,
)


class TestTableLeafCell:
    def test_roundtrip(self):
        c1 = TableLeafCell(42, b'hello world')
        data = c1.serialize()
        c2 = TableLeafCell.parse(data)
        assert c2.rowid == 42
        assert c2.payload == b'hello world'
        assert c2.payload_length == 11

    def test_large_rowid(self):
        c1 = TableLeafCell(2**48, b'data')
        data = c1.serialize()
        c2 = TableLeafCell.parse(data)
        assert c2.rowid == 2**48

    def test_empty_payload(self):
        c1 = TableLeafCell(1, b'')
        data = c1.serialize()
        c2 = TableLeafCell.parse(data)
        assert c2.rowid == 1
        assert c2.payload == b''
        assert c2.payload_length == 0


class TestTableInteriorCell:
    def test_roundtrip(self):
        c1 = TableInteriorCell(5, 100)
        data = c1.serialize()
        c2 = TableInteriorCell.parse(data)
        assert c2.left_child_page == 5
        assert c2.key == 100

    def test_large_values(self):
        c1 = TableInteriorCell(99999, 2**60)
        data = c1.serialize()
        c2 = TableInteriorCell.parse(data)
        assert c2.left_child_page == 99999
        assert c2.key == 2**60


class TestIndexLeafCell:
    def test_roundtrip(self):
        payload = b'\x01\x02\x03\x04'
        c1 = IndexLeafCell(payload)
        data = c1.serialize()
        c2 = IndexLeafCell.parse(data)
        assert c2.payload == payload
        assert c2.payload_length == 4

    def test_empty(self):
        c1 = IndexLeafCell(b'')
        data = c1.serialize()
        c2 = IndexLeafCell.parse(data)
        assert c2.payload == b''
        assert c2.payload_length == 0


class TestIndexInteriorCell:
    def test_roundtrip(self):
        payload = b'\x05\x06\x07'
        c1 = IndexInteriorCell(7, payload)
        data = c1.serialize()
        c2 = IndexInteriorCell.parse(data)
        assert c2.left_child_page == 7
        assert c2.payload == payload
        assert c2.payload_length == 3

    def test_large_payload(self):
        payload = bytes(range(200))
        c1 = IndexInteriorCell(12345, payload)
        data = c1.serialize()
        c2 = IndexInteriorCell.parse(data)
        assert c2.left_child_page == 12345
        assert c2.payload == payload
