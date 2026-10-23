package net.webstas.ariahealth

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class ScaleKeyTest {
    private val provisionUuidLe = "26f33a01-52a8-414b-99a2-1db75c99c032"
        .replace("-", "").chunked(2).reversed().map { it.toInt(16).toByte() }.toByteArray()

    /** A throwaway key, not anyone's real one. */
    private val key = ByteArray(16) { it.toByte() }

    private fun record(received: Boolean, att: ByteArray): ByteArray {
        val l2 = ByteBuffer.allocate(4 + att.size).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            .putShort(att.size.toShort()).putShort(4).put(att).array()
        val acl = ByteBuffer.allocate(5 + l2.size).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            .put(2).putShort((0x0040 or (2 shl 12)).toShort()).putShort(l2.size.toShort()).put(l2).array()
        return ByteBuffer.allocate(24 + acl.size)
            .putInt(acl.size).putInt(acl.size).putInt(if (received) 1 else 0).putInt(0).putLong(0)
            .put(acl).array()
    }

    private fun declaration(valueHandle: Int, uuidLe: ByteArray): ByteArray =
        ByteBuffer.allocate(2 + 21).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            .put(0x09).put(21).putShort((valueHandle - 1).toShort()).put(0x0A)
            .putShort(valueHandle.toShort()).put(uuidLe).array()

    private fun write(handle: Int, value: ByteArray): ByteArray =
        ByteBuffer.allocate(3 + value.size).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            .put(0x12).putShort(handle.toShort()).put(value).array()

    private fun log(vararg writes: ByteArray): ByteArray {
        val out = ByteArrayOutputStream()
        out.write("btsnoop\u0000".toByteArray(Charsets.ISO_8859_1))
        out.write(ByteBuffer.allocate(8).putInt(1).putInt(1002).array())
        out.write(record(true, declaration(0x1F, provisionUuidLe)))
        writes.forEach { out.write(record(false, it)) }
        return out.toByteArray()
    }

    @Test fun findsTheKeyWrittenToTheProvisionCharacteristic() {
        val bytes = log(write(0x1F, ByteArray(1)), write(0x1F, key))
        assertEquals(listOf(key.joinToString("") { "%02x".format(it) }), ScaleKey.find(ByteArrayInputStream(bytes)))
    }

    @Test fun ignoresOtherHandlesAndWrongLengths() {
        val bytes = log(write(0x20, key), write(0x1F, ByteArray(15)))
        assertTrue(ScaleKey.find(ByteArrayInputStream(bytes)).isEmpty())
    }

    @Test fun readsALogInsideAZip() {
        val zipped = ByteArrayOutputStream().also { bytes ->
            ZipOutputStream(bytes).use { zip ->
                zip.putNextEntry(ZipEntry("FS/data/misc/bluetooth/logs/btsnoop_hci.log"))
                zip.write(log(write(0x1F, key)))
                zip.closeEntry()
            }
        }.toByteArray()
        assertEquals(1, ScaleKey.find(ByteArrayInputStream(zipped)).size)
    }

    @Test fun notALogGivesNothing() {
        assertTrue(ScaleKey.find(ByteArrayInputStream("hello".toByteArray())).isEmpty())
        assertTrue(ScaleKey.find(ByteArrayInputStream(ByteArray(0))).isEmpty())
    }
}
