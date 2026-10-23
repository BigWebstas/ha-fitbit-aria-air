package net.webstas.ariahealth

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import com.hivemq.client.mqtt.MqttGlobalPublishFilter
import com.hivemq.client.mqtt.datatypes.MqttQos
import com.hivemq.client.mqtt.mqtt5.Mqtt5AsyncClient
import com.hivemq.client.mqtt.mqtt5.Mqtt5Client
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date

class MqttService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private lateinit var settings: Settings
    private var client: Mqtt5AsyncClient? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        settings = Settings(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            settings.enabled = false
            settings.status = "Stopped"
            stopSelf()
            return START_NOT_STICKY
        }
        startForeground(NOTIFICATION_ID, notification("Connecting…"), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        connect()
        return START_STICKY
    }

    private fun connect() {
        client?.disconnect()
        if (settings.host.isBlank()) {
            fail("Set the broker address first")
            return
        }
        val builder = Mqtt5Client.builder()
            .identifier(settings.clientId)
            .serverHost(settings.host)
            .serverPort(settings.port)
            .automaticReconnectWithDefaultConfig()
            .addConnectedListener { setStatus("Connected, waiting for weigh-ins") }
            .addDisconnectedListener { setStatus("Disconnected, retrying…") }
        if (settings.username.isNotEmpty()) {
            builder.simpleAuth()
                .username(settings.username)
                .password(settings.password.toByteArray())
                .applySimpleAuth()
        }
        val mqtt = builder.buildAsync()
        client = mqtt

        mqtt.publishes(MqttGlobalPublishFilter.ALL) { publish ->
            val payload = String(publish.payloadAsBytes)
            scope.launch { handle(payload) }
        }
        // Keep the session so the broker holds readings while the phone is offline.
        mqtt.connectWith()
            .cleanStart(false)
            .sessionExpiryInterval(7 * 24 * 3600)
            .send()
            .thenCompose {
                mqtt.subscribeWith().topicFilter(settings.topic).qos(MqttQos.AT_LEAST_ONCE).send()
            }
            .whenComplete { _, error ->
                if (error != null) setStatus("Connection failed: ${error.message}")
            }
    }

    private suspend fun handle(payload: String) {
        val weighIn = WeighIn.parse(payload, defaultUnit = if (settings.imperial) "lb" else "kg")
        if (weighIn == null) {
            settings.lastResult = "Ignored an unreadable message"
            return
        }
        val summary = "%.1f %s at %s".format(
            if (settings.imperial) weighIn.pounds else weighIn.kilograms,
            if (settings.imperial) "lb" else "kg",
            DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date.from(weighIn.time)),
        )
        settings.lastResult = try {
            if (!HealthWriter.hasPermission(this)) {
                "Not saved (Health Connect permission missing): $summary"
            } else {
                HealthWriter.write(this, weighIn)
                "Saved $summary"
            }
        } catch (e: Exception) {
            "Not saved (${e.message}): $summary"
        }
        notify(settings.lastResult)
    }

    private fun setStatus(text: String) {
        settings.status = text
        notify(text)
    }

    private fun fail(text: String) {
        setStatus(text)
        stopSelf()
    }

    private fun notify(text: String) {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(text))
    }

    private fun notification(text: String): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "Connection", NotificationManager.IMPORTANCE_LOW),
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        return Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_info_details)
            .setContentTitle("Aria Health Bridge")
            .setContentText(text)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        client?.disconnect()
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val CHANNEL = "connection"
        private const val NOTIFICATION_ID = 1
        const val ACTION_STOP = "net.webstas.ariahealth.STOP"

        fun start(context: Context) {
            context.startForegroundService(Intent(context, MqttService::class.java))
        }

        fun stop(context: Context) {
            context.startService(Intent(context, MqttService::class.java).setAction(ACTION_STOP))
        }
    }
}
