"""Bit-level operations: varint encoding/decoding, twos complement."""


def decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode a SQLite varint starting at data[offset].

    SQLite varint encoding:
      1 byte:  0x00..0xF0        -> value = byte
      2 bytes: 0xF1..0xF8        -> value = (a0-241)*256 + a1 + 240 (241..2287)
      3 bytes: 0xF9              -> value = (a1<<8) + a2 + 2288   (2288..67823)
      4..9 bytes: 0xFA..0xFF     -> count = a0-0xF6 data bytes follow in big-endian
    """
    if offset >= len(data):
        raise ValueError("Unexpected end of data decoding varint")

    a0 = data[offset]

    if a0 <= 0xF0:
        return a0, 1

    if a0 <= 0xF8:
        if offset + 1 >= len(data):
            raise ValueError("Unexpected end of data decoding 2-byte varint")
        a1 = data[offset + 1]
        value = (a0 - 241) * 256 + a1 + 240
        return value, 2

    if a0 == 0xF9:
        if offset + 2 >= len(data):
            raise ValueError("Unexpected end of data decoding 3-byte varint")
        a1 = data[offset + 1]
        a2 = data[offset + 2]
        value = (a1 << 8) + a2 + 2288
        return value, 3

    # 4..9 bytes: a0 >= 0xFA
    total = a0 - 0xF6  # 0xFA->4, 0xFB->5, ..., 0xFF->9
    n_data = total - 1
    if offset + total > len(data):
        raise ValueError("Unexpected end of data decoding multi-byte varint")
    result = 0
    for i in range(n_data):
        result = (result << 8) | data[offset + 1 + i]
    return result, total


def encode_varint(value: int) -> bytes:
    """Encode an integer as a SQLite varint (1-9 bytes)."""
    if value < 0:
        raise ValueError(f"Cannot encode negative varint: {value}")

    if value <= 240:
        return bytes([value])

    if value <= 2287:
        v = value - 240
        return bytes([(v // 256) + 241, v % 256])

    if value <= 67823:
        v = value - 2288
        return bytes([0xF9, (v >> 8) & 0xFF, v & 0xFF])

    # 4..9 bytes
    for total in range(4, 10):
        max_val = (1 << (8 * (total - 1))) - 1
        if value <= max_val:
            a0 = 0xF9 + (total - 3)  # 0xFA for 4, 0xFF for 9
            data = value.to_bytes(total - 1, 'big')
            return bytes([a0]) + data

    raise ValueError(f"Varint too large: {value}")


def decode_twos_complement(data: bytes) -> int:
    """Decode big-endian twos complement integer of arbitrary byte length."""
    value = int.from_bytes(data, 'big', signed=False)
    if data and (data[0] & 0x80):
        bits = len(data) * 8
        value -= 1 << bits
    return value


def encode_twos_complement(value: int, byte_count: int) -> bytes:
    """Encode integer as big-endian twos complement with exact byte count."""
    if value < 0:
        value += 1 << (byte_count * 8)
    return value.to_bytes(byte_count, 'big', signed=False)
