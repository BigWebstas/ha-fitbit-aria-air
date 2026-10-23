"""Decode weigh-in messages from a Fitbit Aria Air (FB203).

The scale sends each weigh-in as a 19-byte indication on a vendor
characteristic. The layout (verified against captured traffic and the
Fitbit Android app's own parser) is::

    bytes 0-7    nonce            (8 bytes)
    bytes 8-15   CCM auth tag     (8 bytes)
    bytes 16-18  ciphertext       (3 bytes)

The message is AES-128-CCM encrypted with a per-scale key, the same 16 bytes the
Fitbit app writes to the scale when it provisions it. The 3 plaintext bytes are
``[unit flag] [weight as little-endian uint16, in hundredths]``.

This module has no Home Assistant imports so it can be tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

NONCE_LEN = 8
TAG_LEN = 8
PACKET_LEN = 19
KEY_LEN = 16


class DecodeError(ValueError):
    """Raised when a message cannot be authenticated or parsed."""


@dataclass(frozen=True, slots=True)
class WeighIn:
    """One decoded weight reading."""

    value: float
    unit_flag: int


def parse_key(text: str) -> bytes:
    """Turn a user-entered key into 16 raw bytes.

    Accepts hex with optional spaces, colons or dashes. Raises ``ValueError``
    for anything that is not exactly 16 bytes.
    """
    cleaned = "".join(ch for ch in text if ch not in " :-\t\n")
    key = bytes.fromhex(cleaned)
    if len(key) != KEY_LEN:
        raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    return key


def decode_weigh_in(key: bytes, packet: bytes) -> WeighIn:
    """Authenticate and decrypt a 19-byte weigh-in indication."""
    if len(packet) != PACKET_LEN:
        raise DecodeError(f"expected {PACKET_LEN} bytes, got {len(packet)}")

    nonce = bytes(packet[:NONCE_LEN])
    tag = bytes(packet[NONCE_LEN : NONCE_LEN + TAG_LEN])
    ciphertext = bytes(packet[NONCE_LEN + TAG_LEN :])

    try:
        # ``cryptography`` expects ciphertext followed by the tag.
        plain = AESCCM(key, tag_length=TAG_LEN).decrypt(nonce, ciphertext + tag, None)
    except InvalidTag as err:
        raise DecodeError("integrity check failed (wrong key or corrupt data)") from err

    if len(plain) < 3:
        raise DecodeError(f"unexpected plaintext length {len(plain)}")

    return WeighIn(
        value=int.from_bytes(plain[1:3], "little") / 100,
        unit_flag=plain[0],
    )
