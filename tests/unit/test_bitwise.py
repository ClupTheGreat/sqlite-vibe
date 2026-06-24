"""Tests for bitwise.py — varint encoding/decoding, twos complement."""

import pytest
from pysqlite.bitwise import (
    decode_varint, encode_varint,
    decode_twos_complement, encode_twos_complement,
)


class TestVarint:
    def test_single_byte_zero(self):
        assert encode_varint(0) == b'\x00'
        val, n = decode_varint(b'\x00')
        assert val == 0 and n == 1

    def test_single_byte_max(self):
        assert encode_varint(240) == b'\xf0'
        val, n = decode_varint(b'\xf0')
        assert val == 240 and n == 1

    def test_two_byte_min(self):
        assert encode_varint(241) == b'\xf1\x01'
        val, n = decode_varint(b'\xf1\x01')
        assert val == 241 and n == 2

    def test_two_byte_max(self):
        # 2287-240 = 2047; 2047//256 = 7, 2047%256 = 255
        assert encode_varint(2287) == b'\xf8\xff'
        val, n = decode_varint(b'\xf8\xff')
        assert val == 2287 and n == 2

    def test_three_byte_min(self):
        # 2288-2288 = 0; byte1=0, byte2=0
        assert encode_varint(2288) == b'\xf9\x00\x00'
        val, n = decode_varint(b'\xf9\x00\x00')
        assert val == 2288 and n == 3

    def test_three_byte_max(self):
        assert encode_varint(67823) == b'\xf9\xff\xff'
        val, n = decode_varint(b'\xf9\xff\xff')
        assert val == 67823 and n == 3

    def test_four_byte(self):
        # 100,000 needs 4 bytes (a0=0xFA, 3 data bytes = 24 bits)
        encoded = encode_varint(100000)
        assert len(encoded) == 4
        assert encoded[0] == 0xFA
        decoded, n = decode_varint(encoded)
        assert decoded == 100000
        assert n == 4

    def test_nine_byte_max(self):
        encoded = encode_varint(2**64 - 1)
        assert len(encoded) == 9
        assert encoded[0] == 0xFF
        decoded, n = decode_varint(encoded)
        assert decoded == 2**64 - 1
        assert n == 9

    def test_large_values_roundtrip(self):
        for val in [0, 1, 127, 128, 240, 241, 1000, 2287, 2288, 50000, 67823,
                    100000, 2**20, 2**31, 2**40, 2**48, 2**56, 2**63, 2**64 - 1]:
            encoded = encode_varint(val)
            decoded, n = decode_varint(encoded)
            assert decoded == val
            assert n == len(encoded)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            encode_varint(-1)

    def test_decode_offset(self):
        # 0xFA + 3 data bytes = 4 bytes total
        data = bytes([1, 2, 3, 0xFA, 0x00, 0x01, 0x86, 42])
        val, n = decode_varint(data, 0)
        assert val == 1 and n == 1
        val, n = decode_varint(data, 1)
        assert val == 2 and n == 1
        val, n = decode_varint(data, 3)
        # 0xFA, 0x00, 0x01, 0x86 = 4 bytes, value = 0x000186 = 390
        assert val == 390 and n == 4
        # After 4-byte varint, next byte is 42
        assert data[7] == 42

    def test_truncated_data_raises(self):
        # b'\xf1' starts a 2-byte varint but only has 1 byte
        with pytest.raises(ValueError):
            decode_varint(b'\xf1', 0)
        # b'\xf9' starts a 3-byte varint but only has 1 byte
        with pytest.raises(ValueError):
            decode_varint(b'\xf9', 0)
        # b'\xfa' starts a multi-byte varint but has no continuation bytes
        with pytest.raises(ValueError):
            decode_varint(b'\xfa', 0)


class TestTwosComplement:
    def test_positive_8bit(self):
        assert encode_twos_complement(42, 1) == b'\x2a'
        assert decode_twos_complement(b'\x2a') == 42

    def test_negative_8bit(self):
        assert encode_twos_complement(-1, 1) == b'\xff'
        assert decode_twos_complement(b'\xff') == -1

    def test_positive_16bit(self):
        assert encode_twos_complement(1000, 2) == b'\x03\xe8'
        assert decode_twos_complement(b'\x03\xe8') == 1000

    def test_negative_16bit(self):
        assert encode_twos_complement(-1000, 2) == b'\xfc\x18'
        assert decode_twos_complement(b'\xfc\x18') == -1000

    def test_24bit(self):
        val = 123456
        encoded = encode_twos_complement(val, 3)
        assert decode_twos_complement(encoded) == val
        val = -123456
        encoded = encode_twos_complement(val, 3)
        assert decode_twos_complement(encoded) == val

    def test_48bit(self):
        val = 2**40 + 12345
        encoded = encode_twos_complement(val, 6)
        assert decode_twos_complement(encoded) == val

    def test_zero(self):
        assert encode_twos_complement(0, 2) == b'\x00\x00'
        assert decode_twos_complement(b'\x00\x00') == 0

    def test_negative_max(self):
        assert encode_twos_complement(-128, 1) == b'\x80'
        assert decode_twos_complement(b'\x80') == -128
