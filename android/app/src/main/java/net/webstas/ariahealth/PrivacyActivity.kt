package net.webstas.ariahealth

import android.app.Activity
import android.os.Bundle
import android.widget.TextView

/** Shown by Health Connect when someone asks why this app wants weight access. */
class PrivacyActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(TextView(this).apply {
            setPadding(48, 48, 48, 48)
            text = "Aria Health Bridge only writes the weight readings your own scale sends to " +
                "your own MQTT broker into Health Connect. It does not read your health data, " +
                "has no accounts, and sends nothing anywhere else."
        })
    }
}
