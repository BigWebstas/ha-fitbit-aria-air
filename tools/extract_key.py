#!/usr/bin/env python3
"""Find your Aria Air's key in an Android Bluetooth HCI snoop log.

When the Fitbit app sets a scale up it writes a 16-byte value to a vendor
characteristic (UUID 26f33a01-52a8-414b-99a2-1db75c99c032). That value is the key
that protects the scale's weigh-ins. If your snoop log recorded the setup, this
script finds it. Standard library only.

    python3 tools/extract_key.py btsnoop_hci.log

Treat the output as a secret: anyone near your scale who has it can read your
weigh-ins.
"""

from __future__ import annotations

import argparse
import datetime
import struct
import sys
from collections.abc import Iterator

PROVISION_UUID = "26f33a01-52a8-414b-99a2-1db75c99c032"
BTSNOOP_EPOCH_OFFSET_US = 0x00DCDDB30F2F8000  # btsnoop timestamps count from year 0

OP_READ_BY_TYPE_RSP = 0x09
OP_WRITE_REQ = 0x12
OP_WRITE_CMD = 0x52


def records(path: str) -> Iterator[tuple[int, int, bytes]]:
    """Yield (flags, timestamp_us, packet) from a btsnoop file."""
    data = open(path, "rb").read()
    if data[:8] != b"btsnoop\x00":
        sys.exit(f"{path}: not a btsnoop file")
    pos = 16
    while pos + 24 <= len(data):
        _orig, incl, flags, _drops, ts = struct.unpack(">IIIIQ", data[pos : pos + 24])
        pos += 24
        yield flags, ts, data[pos : pos + incl]
        pos += incl


def att_pdus(path: str) -> Iterator[tuple[datetime.datetime, bool, bytes]]:
    """Yield (time, received_from_scale, ATT PDU) after reassembling ACL data."""
    partial: dict[tuple[int, bool], bytearray] = {}
    for flags, ts, pkt in records(path):
        if len(pkt) < 5 or pkt[0] != 2:  # 2 = HCI ACL data
            continue
        handle_flags, length = struct.unpack("<HH", pkt[1:5])
        conn, pb = handle_flags & 0x0FFF, (handle_flags >> 12) & 3
        received = bool(flags & 1)
        key = (conn, received)
        if pb in (0, 2):
            partial[key] = bytearray(pkt[5 : 5 + length])
        elif pb == 1 and key in partial:
            partial[key] += pkt[5 : 5 + length]
        else:
            continue
        buf = partial[key]
        if len(buf) < 4:
            continue
        l2_len, cid = struct.unpack("<HH", bytes(buf[:4]))
        if len(buf) - 4 < l2_len:
            continue
        del partial[key]
        if cid == 4:  # ATT
            when = datetime.datetime.fromtimestamp((ts - BTSNOOP_EPOCH_OFFSET_US) / 1e6)
            yield when, received, bytes(buf[4 : 4 + l2_len])


def uuid_str(raw: bytes) -> str:
    """Format a little-endian 16- or 128-bit UUID."""
    if len(raw) == 2:
        return f"0000{raw[::-1].hex()}-0000-1000-8000-00805f9b34fb"
    h = raw[::-1].hex()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def find_keys(path: str) -> list[tuple[datetime.datetime, bytes]]:
    """Return every 16-byte write to the provisioning characteristic."""
    handle_uuid: dict[int, str] = {}
    found: list[tuple[datetime.datetime, bytes]] = []
    for when, received, pdu in att_pdus(path):
        op = pdu[0]
        if received and op == OP_READ_BY_TYPE_RSP and len(pdu) > 2:
            size = pdu[1]
            if size in (7, 21):  # characteristic declarations: 16- or 128-bit UUID
                for i in range(2, len(pdu) - size + 1, size):
                    value_handle = struct.unpack("<H", pdu[i + 3 : i + 5])[0]
                    handle_uuid[value_handle] = uuid_str(pdu[i + 5 : i + size])
        elif not received and op in (OP_WRITE_REQ, OP_WRITE_CMD) and len(pdu) > 3:
            handle = struct.unpack("<H", pdu[1:3])[0]
            value = pdu[3:]
            if handle_uuid.get(handle) == PROVISION_UUID and len(value) == 16:
                found.append((when, value))
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", help="btsnoop_hci.log pulled from an Android phone")
    parser.add_argument("--all", action="store_true", help="show every candidate, not just the latest")
    args = parser.parse_args()

    keys = find_keys(args.log)
    if not keys:
        sys.exit(
            "No key found. The log must include the moment the Fitbit app set the "
            "scale up (or re-linked it). See the README."
        )
    shown = keys if args.all else keys[-1:]
    for when, key in shown:
        print(f"{when:%Y-%m-%d %H:%M:%S}  {key.hex()}")
    if len(keys) > 1 and not args.all:
        print(f"({len(keys)} candidates in the log; showing the latest. Use --all to list them.)", file=sys.stderr)


if __name__ == "__main__":
    main()
