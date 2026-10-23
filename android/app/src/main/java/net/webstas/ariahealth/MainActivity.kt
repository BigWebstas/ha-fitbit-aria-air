package net.webstas.ariahealth

import android.Manifest
import android.content.ClipData
import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Context
import android.os.PersistableBundle
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import android.content.SharedPreferences
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private lateinit var settings: Settings
    private lateinit var host: EditText
    private lateinit var port: EditText
    private lateinit var user: EditText
    private lateinit var pass: EditText
    private lateinit var topic: EditText
    private lateinit var imperial: Switch
    private lateinit var health: TextView
    private lateinit var status: TextView
    private lateinit var last: TextView
    private lateinit var keyResult: TextView

    private val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, _ -> runOnUiThread { refresh() } }

    private val healthPermission = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract(),
    ) { refresh() }
    private val pickLog = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) findKey(uri)
    }
    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = Settings(this)

        fun field(label: String, value: String, password: Boolean = false, number: Boolean = false): EditText {
            return EditText(this).apply {
                hint = label
                setText(value)
                if (password) inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                if (number) inputType = InputType.TYPE_CLASS_NUMBER
                if (!password && !number) inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            }
        }

        host = field("Broker address (e.g. 192.168.1.50)", settings.host)
        port = field("Port", settings.port.toString(), number = true)
        user = field("Username", settings.username)
        pass = field("Password", settings.password, password = true)
        topic = field("Topic", settings.topic)
        imperial = Switch(this).apply {
            text = "Imperial units (lb) instead of metric (kg)"
            isChecked = settings.imperial
            setOnCheckedChangeListener { _, checked -> settings.imperial = checked }
        }
        health = TextView(this)
        status = TextView(this)
        last = TextView(this)
        keyResult = TextView(this).apply { setTextIsSelectable(true) }

        fun button(label: String, onClick: () -> Unit) = Button(this).apply {
            text = label
            setOnClickListener { onClick() }
        }

        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 96, 48, 48)
            listOf(
                host, port, user, pass, topic, imperial,
                health,
                button("Allow saving weight to Health Connect") {
                    healthPermission.launch(HealthWriter.PERMISSIONS)
                },
                button("Save and start") { saveAndStart() },
                button("Stop") { MqttService.stop(this@MainActivity) },
                status, last,
                TextView(this@MainActivity).apply {
                    setPadding(0, 64, 0, 0)
                    text = "Need your scale's key for Home Assistant? Pick a Bluetooth log (or a bug report zip) from when the Fitbit app set the scale up."
                },
                button("Find my scale key in a log") { pickLog.launch(arrayOf("*/*")) },
                keyResult,
            ).forEach { addView(it) }
        }
        setContentView(ScrollView(this).apply { addView(column) })
        notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun findKey(uri: Uri) {
        keyResult.text = "Searching…"
        lifecycleScope.launch {
            val keys = try {
                withContext(Dispatchers.IO) {
                    contentResolver.openInputStream(uri)?.use { ScaleKey.find(it) } ?: emptyList()
                }
            } catch (e: Exception) {
                keyResult.text = "Could not read that file: ${e.message}"
                return@launch
            }
            if (keys.isEmpty()) {
                keyResult.text = "No key found. The log must include the moment the Fitbit app set the scale up."
                return@launch
            }
            val latest = keys.last()
            keyResult.text = "Key: $latest" +
                if (keys.size > 1) "\n(${keys.size} candidates found; this is the latest.)" else ""
            copyKey(latest)
        }
    }

    private fun copyKey(key: String) {
        val clip = ClipData.newPlainText("Aria Air key", key)
        clip.description.extras = PersistableBundle().apply {
            putBoolean(ClipDescription.EXTRA_IS_SENSITIVE, true)
        }
        getSystemService(Context.CLIPBOARD_SERVICE).let { it as ClipboardManager }.setPrimaryClip(clip)
        keyResult.append("\nCopied to the clipboard. Paste it into Home Assistant, then clear it.")
    }

    private fun saveAndStart() {
        settings.host = host.text.toString()
        settings.port = port.text.toString().toIntOrNull() ?: 1883
        settings.username = user.text.toString()
        settings.password = pass.text.toString()
        settings.topic = topic.text.toString().ifBlank { "aria_air/weigh_in" }
        settings.enabled = true
        MqttService.start(this)
    }

    private fun refresh() {
        status.text = "Connection: ${settings.status}"
        last.text = "Last weigh-in: ${settings.lastResult}"
        lifecycleScope.launch {
            health.text = when {
                !HealthWriter.available(this@MainActivity) -> "Health Connect: not available on this phone"
                HealthWriter.hasPermission(this@MainActivity) -> "Health Connect: allowed"
                else -> "Health Connect: permission needed"
            }
            health.visibility = View.VISIBLE
        }
    }

    override fun onResume() {
        super.onResume()
        settings.prefs.registerOnSharedPreferenceChangeListener(listener)
        refresh()
    }

    override fun onPause() {
        settings.prefs.unregisterOnSharedPreferenceChangeListener(listener)
        super.onPause()
    }
}
