package net.webstas.ariahealth

import android.content.Context
import android.content.SharedPreferences
import java.util.Locale
import java.util.UUID

/** Connection settings and last-result status, kept in private app storage. */
class Settings(context: Context) {
    val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences("settings", Context.MODE_PRIVATE)

    var host: String
        get() = prefs.getString("host", "") ?: ""
        set(v) = prefs.edit().putString("host", v.trim()).apply()
    var port: Int
        get() = prefs.getInt("port", 1883)
        set(v) = prefs.edit().putInt("port", v).apply()
    var username: String
        get() = prefs.getString("username", "") ?: ""
        set(v) = prefs.edit().putString("username", v).apply()
    var password: String
        get() = prefs.getString("password", "") ?: ""
        set(v) = prefs.edit().putString("password", v).apply()
    var topic: String
        get() = prefs.getString("topic", "aria_air/weigh_in") ?: "aria_air/weigh_in"
        set(v) = prefs.edit().putString("topic", v.trim()).apply()
    var enabled: Boolean
        get() = prefs.getBoolean("enabled", false)
        set(v) = prefs.edit().putBoolean("enabled", v).apply()
    /** Display units, and the unit assumed for messages that don't name one. */
    var imperial: Boolean
        get() = prefs.getBoolean("imperial", Locale.getDefault().country == "US")
        set(v) = prefs.edit().putBoolean("imperial", v).apply()
    var status: String
        get() = prefs.getString("status", "Not started") ?: ""
        set(v) = prefs.edit().putString("status", v).apply()
    var lastResult: String
        get() = prefs.getString("last_result", "No weigh-in yet") ?: ""
        set(v) = prefs.edit().putString("last_result", v).apply()

    /** A fixed client id lets the broker queue messages while the phone is offline. */
    val clientId: String
        get() = prefs.getString("client_id", null) ?: "aria-health-${UUID.randomUUID().toString().take(8)}"
            .also { prefs.edit().putString("client_id", it).apply() }
}
