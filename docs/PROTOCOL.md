# Fitbit Aria Air (FB203) Bluetooth protocol notes

These notes describe how the Aria Air talks over Bluetooth Low Energy, as worked
out from (a) captures of the Fitbit Android app syncing the scale and (b) the
app's own parsing code. They are for interoperating with a scale **you own** and
the weigh-ins **you** make. Nothing here is endorsed by Fitbit or Google, and
nothing was verified on firmware other than `A16` (hardware `H01`).

## Device summary

| | |
|---|---|
| Model | Fitbit Aria Air, `FB203` |
| Advertised name | `Aria Air` |
| Radio | Bluetooth LE (no Wi-Fi) |
| Pairing | None. The scale accepts an unbonded connection |
| Awake only when | someone is standing on it; asleep it drops a connection within a second |

## Advertisement

The scale advertises continuously, even asleep, with:

- local name `Aria Air`
- advertising flags `0x05`
- manufacturer data, company code `0x018E`, 8 bytes: `[00] [status] [6-byte scale address]`

`status` is `1` while the scale is awake and `0` otherwise (observed to flip to `1`
when stepped on and back to `0` seconds later). The scale stops advertising while
connected.

The manufacturer data is not in the primary advertisement (flags, a partial
`181D` UUID list and the name). It appears to arrive in the scan response, so a
passive scan never sees the status change, and a Bluetooth proxy that scans
actively only in short windows can miss it.

## GATT layout

| Service | Characteristics |
|---|---|
| Generic Access `1800` | Device Name, Appearance, Preferred Connection Parameters |
| Device Information `180A` | Manufacturer `Fitbit`, Model `FB203`, Serial `F-31-<address>`, Hardware `H01`, Firmware `A16`, Software `A16`, plus a stray Glucose Feature |
| Weight Scale `181D` | `67b0ab2c-8323-427a-b1c9-70324bb5e228` (vendor, **indicate**, has a CCCD) and the standard Weight Scale Feature `2A9E` (reads `00 00 00 00`) |
| Vendor `26f33a00-52a8-414b-99a2-1db75c99c032` | `26f33a01-...` (read/write): one byte of **provision status** |
| Nordic legacy DFU `00001530-1212-efde-1523-785feabcd123` | firmware update. **Never write to it**; a bad write can brick the scale |

Note that although the Weight Scale service is advertised, the weight does **not**
use the standard `2A9D` characteristic.

## Provisioning

`26f33a01-...` holds one byte:

- `00`: not linked. The app writes a random-looking **16-byte value** to the same
  characteristic. This is the scale's key (see below).
- `01`: linked.

Resetting the scale (hold the button on the back for about 5 seconds until `CLR`
shows) and setting it up again returns it to `00` and produces a new key.

## Receiving a weigh-in

1. Connect (the scale only accepts while awake; expect several early refusals
   for a few seconds after someone steps on).
2. Enable messages: write `01 00` to the CCCD of `67b0ab2c-...` (descriptor
   `2902`, the handle right after the characteristic value).
3. The scale sends **indications** on `67b0ab2c-...`. Confirm each one (the ATT
   layer does this automatically).

The CCCD value matters: the characteristic declares *indicate*, but the Fitbit app
writes `0x0001` (the notification bit) and that is what the scale answers. A
client that writes `0x0002` because the characteristic only declares indicate may
receive nothing.

A weigh-in usually arrives within a few seconds, and is typically repeated a short
while later. Extra readings with other values were also seen; their cause is not
understood.

## Message format

Each message is 19 bytes:

| Bytes | Content |
|---|---|
| 0-7 | nonce |
| 8-15 | AES-CCM authentication tag (8 bytes) |
| 16-18 | ciphertext (3 bytes) |

Decrypt with **AES-128-CCM**, no associated data, the 8-byte nonce above, the
8-byte tag, and the scale's key. The 3 plaintext bytes are:

| Byte | Meaning |
|---|---|
| 0 | unit flag (always `1` in every capture; the mapping to kg or lb was not established, so the integration lets you choose) |
| 1-2 | weight, little-endian unsigned, in **hundredths** (`0x08FC` = 2300 = 23.00) |

A message that fails the CCM tag check is not a valid reading (wrong key,
corruption or tampering).

The nonce contains a running clock in seconds (byte 3) between two mirrored pairs of
bytes (bytes 1-2 and 4-5 repeat in reverse order). This is a quirk of the framing,
not something the decoder needs.

## The key

The key is the 16-byte value written to `26f33a01-...` when the Fitbit app links
the scale. The Android Bluetooth HCI snoop log of that moment contains it in
plain text, which is how `tools/extract_key.py` finds it. Whoever has the key and
is within Bluetooth range can read your weigh-ins, so keep it private. Nothing
here lets you read anyone else's scale without that key.

## Open questions

- Which unit flag value means kilograms and which pounds.
- Why some weigh-ins produce several messages, including readings that do not
  match any real weigh-in.
- Whether the scale stores readings made while no client is subscribed. In every
  capture a client was subscribed during the weigh-in.
- Behaviour on firmware other than `A16`.

## How this was worked out

1. A Bluetooth LE scan showed the advertisement above and the standard Weight
   Scale service UUID.
2. Connecting from a PC listed the GATT table (above).
3. Android's Bluetooth HCI snoop log, pulled with `adb bugreport`, recorded the
   Fitbit app's own conversation: service discovery, the provision-status read,
   the 16-byte write, the CCCD write of `01 00` and the 19-byte indications.
4. The Fitbit app's decoding code uses AES-CCM and rejects messages that fail a
   MAC check. Testing CCM against the captured messages, with the 16-byte value
   as the key, authenticated every one, and the decrypted weights matched what
   was shown on the scale.
