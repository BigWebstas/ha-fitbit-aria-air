package net.webstas.ariahealth

import org.json.JSONException
import org.json.JSONObject
import java.time.Instant
import java.time.format.DateTimeParseException

/** One weigh-in, always in kilograms. */
data class WeighIn(val kilograms: Double, val time: Instant) {
    /** The weight in pounds, for display. */
    val pounds: Double get() = kilograms / LB_TO_KG

    /** Stable per reading, so a repeated message can't create a second record. */
    val recordId: String get() = "aria-air-${time.epochSecond}"

    companion object {
        const val LB_TO_KG = 0.45359237
        private val SANE_KG = 2.0..635.0

        /**
         * Parses `{"value": 72.4, "unit": "lb", "time": "2026-10-22T07:30:00Z"}`.
         * `unit` defaults to [defaultUnit] (kg or lb), `time` to [now]. Returns null if it isn't a usable reading.
         */
        fun parse(payload: String, now: Instant = Instant.now(), defaultUnit: String = "kg"): WeighIn? {
            val json = try {
                JSONObject(payload)
            } catch (_: JSONException) {
                return null
            }
            val value = json.optDouble("value", Double.NaN)
            if (value.isNaN()) return null
            val kg = when (json.optString("unit", defaultUnit).lowercase()) {
                "kg", "kgs" -> value
                "lb", "lbs" -> value * LB_TO_KG
                else -> return null
            }
            if (kg !in SANE_KG) return null
            val time = try {
                json.optString("time").takeIf { it.isNotBlank() }?.let(Instant::parse) ?: now
            } catch (_: DateTimeParseException) {
                return null
            }
            return WeighIn(kg, time)
        }
    }
}
