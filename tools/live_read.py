#!/usr/bin/env python3
"""Read an Aria Air directly from a Linux machine (no phone, no Home Assistant).

Useful to check your key and that the scale talks to your Bluetooth adapter
before setting up the integration. Needs Linux/BlueZ, Python 3.10+ and the
``cryptography`` package. Run as a normal user.

    export ARIA_KEY=<32 hex characters>
    python3 tools/live_read.py --address AA:BB:CC:DD:EE:FF --adapter 11:22:33:44:55:66

``--adapter`` is your computer's Bluetooth address (``bluetoothctl list``). Stop
any other app (including the Fitbit app) from talking to the scale first, then
step on it. The script retries until the scale wakes, subscribes the way the
Fitbit app does, and prints each decoded weight.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "fitbit_aria_air"),
)
from decode import DecodeError, decode_weigh_in, parse_key  # noqa: E402

ATT_CID = 4
LE_PUBLIC = 1
OP_READ_BY_TYPE_REQ, OP_READ_BY_TYPE_RSP = 0x08, 0x09
OP_WRITE_REQ, OP_WRITE_RSP = 0x12, 0x13
OP_NOTIFY, OP_INDICATE, OP_CONFIRM = 0x1B, 0x1D, 0x1E

WEIGHT_UUID = bytes.fromhex("67b0ab2c-8323-427a-b1c9-70324bb5e228".replace("-", ""))[::-1]


def find_handle(sock: socket.socket, uuid_le: bytes) -> int:
    """Return the value handle of a characteristic, via a characteristic scan."""
    start = 1
    while start < 0xFFFF:
        sock.send(bytes([OP_READ_BY_TYPE_REQ]) + start.to_bytes(2, "little") + b"\xff\xff\x03\x28")
        rsp = sock.recv(512)
        if rsp[0] != OP_READ_BY_TYPE_RSP:
            break
        size = rsp[1]
        for i in range(2, len(rsp) - size + 1, size):
            if rsp[i + 5 : i + size] == uuid_le:
                return int.from_bytes(rsp[i + 3 : i + 5], "little")
        start = int.from_bytes(rsp[len(rsp) - size : len(rsp) - size + 2], "little") + 1
    raise RuntimeError("characteristic not found; is this an Aria Air?")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--address", required=True, help="scale's Bluetooth address")
    parser.add_argument("--adapter", required=True, help="this computer's Bluetooth address")
    parser.add_argument("--seconds", type=int, default=180, help="how long to keep trying (default 180)")
    args = parser.parse_args()

    key_text = os.environ.get("ARIA_KEY")
    if not key_text:
        sys.exit("Set ARIA_KEY to your 32-hex-character key first.")
    key = parse_key(key_text)

    deadline = time.time() + args.seconds
    print("Waiting for the scale. Step on it now...")
    while time.time() < deadline:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        sock.bind((args.adapter, 0, ATT_CID, LE_PUBLIC))
        sock.settimeout(2.5)
        try:
            sock.connect((args.address, 0, ATT_CID, LE_PUBLIC))
        except OSError:
            sock.close()
            time.sleep(0.4)
            continue

        print("Connected.")
        try:
            sock.settimeout(4)
            weight_handle = find_handle(sock, WEIGHT_UUID)
            cccd = weight_handle + 1  # the switch directly follows the value
            sock.send(bytes([OP_WRITE_REQ]) + cccd.to_bytes(2, "little") + b"\x01\x00")
            if sock.recv(512)[0] != OP_WRITE_RSP:
                print("Scale refused to enable messages.")
            sock.settimeout(1.0)
            while time.time() < deadline:
                try:
                    pdu = sock.recv(512)
                except socket.timeout:
                    continue
                if not pdu:
                    break
                if pdu[0] in (OP_INDICATE, OP_NOTIFY):
                    if pdu[0] == OP_INDICATE:
                        sock.send(bytes([OP_CONFIRM]))
                    try:
                        reading = decode_weigh_in(key, pdu[3:])
                    except DecodeError as err:
                        print(f"Unreadable message: {err}")
                    else:
                        print(f"Weight: {reading.value:.2f} (unit flag {reading.unit_flag})")
        except (OSError, RuntimeError) as err:
            print(f"Session ended: {err}")
        finally:
            sock.close()
        time.sleep(0.5)


if __name__ == "__main__":
    main()
