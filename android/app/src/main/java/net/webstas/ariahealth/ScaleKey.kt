package net.webstas.ariahealth

import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.EOFException
import java.io.InputStream
import java.util.zip.ZipInputStream

/**
 * Finds the scale's key in an Android Bluetooth HCI snoop log.
 *
 * When the Fitbit app links an Aria Air it writes a 16-byte value to a vendor
 * characteristic; that value is the key protecting the scale's weigh-ins. The log
 * (or a bug report zip containing it) records that write. Mirrors tools/extract_key.py.
 */
object ScaleKey {
    private const val PROVISION_UUID = "26f33a01-52a8-414b-99a2-1db75c99c032"
    private const val OP_READ_BY_TYPE_RSP = 0x09
    private const val OP_WRITE_REQ = 0x12
    private const val OP_WRITE_CMD = 0x52
    private const val CID_ATT = 4
    private const val MAX_PACKET = 1 shl 16

    /** Keys found in a btsnoop log or a zip holding one, oldest first, without repeats. */
    fun find(source: InputStream): List<String> {
        val input = BufferedInputStream(source)
        input.mark(4)
        val isZip = input.read() == 'P'.code && input.read() == 'K'.code
        input.reset()
        val keys = if (isZip) fromZip(input) else fromLog(input)
        return keys.map { it.toHex() }.distinct()
    }

    private fun fromZip(input: InputStream): List<ByteArray> {
        val byEntry = LinkedHashMap<String, List<ByteArray>>()
        val zip = ZipInputStream(input)
        while (true) {
            val entry = zip.nextEntry ?: break
            if (!entry.isDirectory && "btsnoop" in entry.name) {
                byEntry[entry.name] = fromLog(zip)
            }
        }
        // "btsnoop_hci.log.last" is the older of the pair.
        return byEntry.entries.sortedBy { !it.key.endsWith(".last") }.flatMap { it.value }
    }

    private fun fromLog(input: InputStream): List<ByteArray> {
        val data = DataInputStream(input)
        val header = ByteArray(16)
        try {
            data.readFully(header)
        } catch (_: EOFException) {
            return emptyList()
        }
        if (String(header, 0, 7, Charsets.ISO_8859_1) != "btsnoop") return emptyList()

        val handleUuid = HashMap<Int, String>()
        val partial = HashMap<Int, ByteArrayOutputStream>()
        val found = ArrayList<ByteArray>()
        while (true) {
            val flags: Int
            val packet: ByteArray
            try {
                data.readInt() // original length
                val included = data.readInt()
                flags = data.readInt()
                data.readInt() // drops
                data.readLong() // timestamp
                if (included < 0 || included > MAX_PACKET) return found
                packet = ByteArray(included)
                data.readFully(packet)
            } catch (_: EOFException) {
                break
            }
            val pdu = attPdu(packet, flags and 1 == 1, partial) ?: continue
            inspect(pdu, flags and 1 == 1, handleUuid, found)
        }
        return found
    }

    /** Reassembles ACL fragments; returns an ATT PDU once a whole one has arrived. */
    private fun attPdu(
        packet: ByteArray,
        received: Boolean,
        partial: HashMap<Int, ByteArrayOutputStream>,
    ): ByteArray? {
        if (packet.size < 5 || packet[0].toInt() != 2) return null // 2 = ACL data
        val handleFlags = le16(packet, 1)
        val length = le16(packet, 3)
        val key = (handleFlags and 0x0FFF) * 2 + if (received) 1 else 0
        val chunk = packet.copyOfRange(5, minOf(packet.size, 5 + length))
        when ((handleFlags shr 12) and 3) {
            0, 2 -> partial[key] = ByteArrayOutputStream().also { it.write(chunk) }
            1 -> partial[key]?.write(chunk) ?: return null
            else -> return null
        }
        val buffer = partial[key]!!.toByteArray()
        if (buffer.size < 4) return null
        val l2Length = le16(buffer, 0)
        if (buffer.size - 4 < l2Length) return null
        partial.remove(key)
        return if (le16(buffer, 2) == CID_ATT) buffer.copyOfRange(4, 4 + l2Length) else null
    }

    private fun inspect(
        pdu: ByteArray,
        received: Boolean,
        handleUuid: HashMap<Int, String>,
        found: MutableList<ByteArray>,
    ) {
        val op = pdu[0].toInt() and 0xFF
        if (received && op == OP_READ_BY_TYPE_RSP && pdu.size > 2) {
            val size = pdu[1].toInt() and 0xFF
            if (size == 7 || size == 21) { // characteristic declarations
                var i = 2
                while (i + size <= pdu.size) {
                    handleUuid[le16(pdu, i + 3)] = uuid(pdu.copyOfRange(i + 5, i + size))
                    i += size
                }
            }
        } else if (!received && (op == OP_WRITE_REQ || op == OP_WRITE_CMD) && pdu.size > 3) {
            val value = pdu.copyOfRange(3, pdu.size)
            if (handleUuid[le16(pdu, 1)] == PROVISION_UUID && value.size == 16) found += value
        }
    }

    private fun le16(b: ByteArray, at: Int) = (b[at].toInt() and 0xFF) or ((b[at + 1].toInt() and 0xFF) shl 8)

    private fun uuid(little: ByteArray): String {
        val hex = little.reversed().joinToString("") { "%02x".format(it) }
        return if (little.size == 2) "0000$hex-0000-1000-8000-00805f9b34fb"
        else "${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-" +
            "${hex.substring(16, 20)}-${hex.substring(20)}"
    }

    private fun ByteArray.toHex() = joinToString("") { "%02x".format(it) }
}
