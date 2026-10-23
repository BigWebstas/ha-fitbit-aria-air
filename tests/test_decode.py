"""Tests for the weigh-in decoder.

The packets are produced with a throwaway test key, so no real scale secret is
stored in this repository.
"""

import os
import sys

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "fitbit_aria_air")
)

from decode import (  # noqa: E402
    DecodeError,
    WeighIn,
    decode_weigh_in,
    parse_key,
)

KEY = bytes(range(16))


def make_packet(key: bytes, weight_hundredths: int, flag: int = 1, nonce: bytes | None = None) -> bytes:
    nonce = nonce or bytes([0x2A, 0x32, 0x89, 0x05, 0x89, 0x32, 0x64, 0xC8])
    plain = bytes([flag]) + weight_hundredths.to_bytes(2, "little")
    sealed = AESCCM(key, tag_length=8).encrypt(nonce, plain, None)
    ciphertext, tag = sealed[:-8], sealed[-8:]
    return nonce + tag + ciphertext  # the scale's wire layout


@pytest.mark.parametrize("hundredths", [2300, 2620, 2740, 3220, 12345])
def test_round_trip(hundredths):
    reading = decode_weigh_in(KEY, make_packet(KEY, hundredths))
    assert reading == WeighIn(value=hundredths / 100, unit_flag=1)


def test_unit_flag_is_passed_through():
    assert decode_weigh_in(KEY, make_packet(KEY, 7000, flag=0)).unit_flag == 0


def test_wrong_key_is_rejected():
    with pytest.raises(DecodeError, match="integrity"):
        decode_weigh_in(bytes(16), make_packet(KEY, 2300))


@pytest.mark.parametrize("index", [0, 5, 10, 15, 18])
def test_tampering_is_rejected(index):
    packet = bytearray(make_packet(KEY, 2300))
    packet[index] ^= 0x01
    with pytest.raises(DecodeError):
        decode_weigh_in(KEY, bytes(packet))


@pytest.mark.parametrize("length", [0, 1, 18, 20, 40])
def test_wrong_length_is_rejected(length):
    with pytest.raises(DecodeError, match="expected"):
        decode_weigh_in(KEY, bytes(length))


def test_parse_key_accepts_common_formats():
    expected = bytes(range(16))
    assert parse_key("000102030405060708090a0b0c0d0e0f") == expected
    assert parse_key("00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F") == expected
    assert parse_key("00:01:02:03:04:05:06:07:08:09:0a:0b:0c:0d:0e:0f") == expected


@pytest.mark.parametrize("bad", ["", "zz", "0011", "00" * 17, "0g" * 16])
def test_parse_key_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_key(bad)
