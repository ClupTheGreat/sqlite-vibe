"""SQLite record encoding/decoding using serial type system."""

import struct
from .bitwise import encode_varint, decode_varint


class Record:
    """A record is a sequence of (serial_type, value) pairs."""

    __slots__ = ('columns',)

    def __init__(self, columns: list[tuple[int, object]]):
        self.columns = columns

    @staticmethod
    def serial_type(value) -> int:
        """Determine the serial type code for a Python value."""
        if value is None:
            return 0
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, int):
            if value == 0:
                return 8
            if value == 1:
                return 9
            if -128 <= value <= 127:
                return 1
            if -32768 <= value <= 32767:
                return 2
            if -8388608 <= value <= 8388607:
                return 3
            if -2147483648 <= value <= 2147483647:
                return 4
            if -140737488355328 <= value <= 140737488355327:
                return 5
            return 6
        if isinstance(value, float):
            return 7
        if isinstance(value, (bytes, bytearray)):
            length = len(value)
            return 12 + 2 * length
        if isinstance(value, str):
            encoded = value.encode('utf-8')
            length = len(encoded)
            return 13 + 2 * length
        raise ValueError(f"Cannot serialize type: {type(value)}")

    @staticmethod
    def serial_type_to_bytes(st: int, value) -> bytes:
        """Convert a Python value to raw bytes given its serial type."""
        if st == 0:
            return b''
        if st == 1:
            return struct.pack('>b', value)
        if st == 2:
            return struct.pack('>h', value)
        if st == 3:
            if value < 0:
                value += 1 << 24
            return value.to_bytes(3, 'big')
        if st == 4:
            return struct.pack('>i', value)
        if st == 5:
            if value < 0:
                value += 1 << 48
            return value.to_bytes(6, 'big')
        if st == 6:
            return struct.pack('>q', value)
        if st == 7:
            return struct.pack('>d', value)
        if st == 8:
            return b''
        if st == 9:
            return b''
        if st >= 12 and st % 2 == 0:
            length = (st - 12) // 2
            if isinstance(value, str):
                value = value.encode('utf-8')
            return bytes(value[:length])
        if st >= 13 and st % 2 == 1:
            length = (st - 13) // 2
            if isinstance(value, str):
                encoded = value.encode('utf-8')
            else:
                encoded = str(value).encode('utf-8')
            return encoded[:length]
        raise ValueError(f"Unknown serial type: {st}")

    @staticmethod
    def bytes_to_value(st: int, data: bytes):
        """Convert raw bytes back to a Python value given serial type."""
        if st == 0:
            return None
        if st == 1:
            return struct.unpack('>b', data)[0]
        if st == 2:
            return struct.unpack('>h', data)[0]
        if st == 3:
            val = int.from_bytes(data, 'big')
            if val >= 1 << 23:
                val -= 1 << 24
            return val
        if st == 4:
            return struct.unpack('>i', data)[0]
        if st == 5:
            val = int.from_bytes(data, 'big')
            if val >= 1 << 47:
                val -= 1 << 48
            return val
        if st == 6:
            return struct.unpack('>q', data)[0]
        if st == 7:
            return struct.unpack('>d', data)[0]
        if st == 8:
            return 0
        if st == 9:
            return 1
        if st >= 12 and st % 2 == 0:
            return data
        if st >= 13 and st % 2 == 1:
            return data.decode('utf-8')
        raise ValueError(f"Unknown serial type: {st}")

    def encode(self) -> bytes:
        """Serialize the record to bytes."""
        serial_types = []
        values_bytes = b''
        for st, value in self.columns:
            serial_types.append(st)
            values_bytes += self.serial_type_to_bytes(st, value)

        header_data = b''
        for st in serial_types:
            header_data += encode_varint(st)

        header_length = len(header_data)
        result = encode_varint(header_length + 1)
        result += header_data
        result += values_bytes
        return result

    @classmethod
    def decode(cls, data: bytes, offset: int = 0) -> tuple['Record', int]:
        """Decode a record from bytes. Returns (Record, bytes_consumed)."""
        header_size, consumed = decode_varint(data, offset)
        offset += consumed
        header_end = offset + header_size - 1

        serial_types = []
        while offset < header_end:
            st, consumed = decode_varint(data, offset)
            serial_types.append(st)
            offset += consumed

        values = []
        for st in serial_types:
            if st == 0:
                values.append((st, None))
            elif st == 8:
                values.append((st, 0))
            elif st == 9:
                values.append((st, 1))
            elif 1 <= st <= 7:
                sizes = {1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 6: 8, 7: 8}
                size = sizes[st]
                val_data = data[offset:offset + size]
                values.append((st, cls.bytes_to_value(st, val_data)))
                offset += size
            elif st >= 12:
                if st % 2 == 0:
                    size = (st - 12) // 2
                else:
                    size = (st - 13) // 2
                val_data = data[offset:offset + size]
                values.append((st, cls.bytes_to_value(st, val_data)))
                offset += size

        return cls(values), offset

    def get_values(self) -> list:
        """Return just the Python values without serial type info."""
        return [v for _, v in self.columns]

    @staticmethod
    def encode_from_values(values: list) -> bytes:
        """Encode a list of Python values directly into a record byte string."""
        columns = [(Record.serial_type(v), v) for v in values]
        return Record(columns).encode()
