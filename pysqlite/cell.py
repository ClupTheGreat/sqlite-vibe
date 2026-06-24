"""B-Tree cell serialization/deserialization for all four cell types."""

from .bitwise import encode_varint, decode_varint


class Cell:
    """Base class for all cell types."""
    __slots__ = ()

    def serialize(self) -> bytes:
        raise NotImplementedError


class TableLeafCell(Cell):
    """Table leaf cell: payload_length, rowid, payload."""
    __slots__ = ('payload_length', 'rowid', 'payload')

    def __init__(self, rowid: int, payload: bytes):
        self.rowid = rowid
        self.payload = payload
        self.payload_length = len(payload)

    def serialize(self) -> bytes:
        return encode_varint(self.payload_length) + encode_varint(self.rowid) + self.payload

    @classmethod
    def parse(cls, data: bytes) -> 'TableLeafCell':
        offset = 0
        payload_length, consumed = decode_varint(data, offset)
        offset += consumed
        rowid, consumed = decode_varint(data, offset)
        offset += consumed
        payload = data[offset:offset + payload_length]
        return cls(rowid, payload)


class TableInteriorCell(Cell):
    """Table interior cell: left_child_page, key."""
    __slots__ = ('left_child_page', 'key')

    def __init__(self, left_child_page: int, key: int):
        self.left_child_page = left_child_page
        self.key = key

    def serialize(self) -> bytes:
        return encode_varint(self.left_child_page) + encode_varint(self.key)

    @classmethod
    def parse(cls, data: bytes) -> 'TableInteriorCell':
        offset = 0
        left_child, consumed = decode_varint(data, offset)
        offset += consumed
        key, consumed = decode_varint(data, offset)
        return cls(left_child, key)


class IndexLeafCell(Cell):
    """Index leaf cell: payload_length, payload."""
    __slots__ = ('payload_length', 'payload')

    def __init__(self, payload: bytes):
        self.payload = payload
        self.payload_length = len(payload)

    def serialize(self) -> bytes:
        return encode_varint(self.payload_length) + self.payload

    @classmethod
    def parse(cls, data: bytes) -> 'IndexLeafCell':
        offset = 0
        payload_length, consumed = decode_varint(data, offset)
        offset += consumed
        payload = data[offset:offset + payload_length]
        return cls(payload)


class IndexInteriorCell(Cell):
    """Index interior cell: left_child_page, payload_length, payload."""
    __slots__ = ('left_child_page', 'payload_length', 'payload')

    def __init__(self, left_child_page: int, payload: bytes):
        self.left_child_page = left_child_page
        self.payload = payload
        self.payload_length = len(payload)

    def serialize(self) -> bytes:
        return (encode_varint(self.left_child_page) +
                encode_varint(self.payload_length) +
                self.payload)

    @classmethod
    def parse(cls, data: bytes) -> 'IndexInteriorCell':
        offset = 0
        left_child, consumed = decode_varint(data, offset)
        offset += consumed
        payload_length, consumed = decode_varint(data, offset)
        offset += consumed
        payload = data[offset:offset + payload_length]
        return cls(left_child, payload)
