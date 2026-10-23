package net.webstas.ariahealth

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant

class WeighInTest {
    private val now = Instant.parse("2026-10-22T12:00:00Z")

    @Test fun kilogramsPassThrough() {
        val w = WeighIn.parse("""{"value": 72.4, "unit": "kg"}""", now)!!
        assertEquals(72.4, w.kilograms, 1e-9)
        assertEquals(now, w.time)
    }

    @Test fun poundsConvert() {
        val w = WeighIn.parse("""{"value": 160, "unit": "lb"}""", now)!!
        assertEquals(72.5747792, w.kilograms, 1e-6)
    }

    @Test fun unitDefaultsToKilograms() {
        assertEquals(80.0, WeighIn.parse("""{"value": 80}""", now)!!.kilograms, 1e-9)
    }

    @Test fun missingUnitFollowsTheDefault() {
        val w = WeighIn.parse("""{"value": 160}""", now, defaultUnit = "lb")!!
        assertEquals(72.5747792, w.kilograms, 1e-6)
        assertEquals(160.0, w.pounds, 1e-9)
    }

    @Test fun usesTheGivenTimeAndStableId() {
        val w = WeighIn.parse("""{"value": 80, "time": "2026-10-22T07:30:00Z"}""", now)!!
        assertEquals(Instant.parse("2026-10-22T07:30:00Z"), w.time)
        assertEquals("aria-air-${w.time.epochSecond}", w.recordId)
    }

    @Test fun rejectsBadInput() {
        assertNull(WeighIn.parse("unknown", now))
        assertNull(WeighIn.parse("""{"value": "x"}""", now))
        assertNull(WeighIn.parse("""{"value": 80, "unit": "stone"}""", now))
        assertNull(WeighIn.parse("""{"value": 80, "time": "yesterday"}""", now))
        assertNull(WeighIn.parse("""{"value": 0.5}""", now))
        assertNull(WeighIn.parse("""{"value": 9000}""", now))
    }
}
