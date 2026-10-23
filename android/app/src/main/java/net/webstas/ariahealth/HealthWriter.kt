package net.webstas.ariahealth

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.WeightRecord
import androidx.health.connect.client.records.metadata.Device
import androidx.health.connect.client.records.metadata.Metadata
import androidx.health.connect.client.units.Mass
import java.time.ZoneId

object HealthWriter {
    val PERMISSIONS = setOf(HealthPermission.getWritePermission(WeightRecord::class))

    fun available(context: Context): Boolean =
        HealthConnectClient.getSdkStatus(context) == HealthConnectClient.SDK_AVAILABLE

    suspend fun hasPermission(context: Context): Boolean =
        available(context) &&
            HealthConnectClient.getOrCreate(context).permissionController
                .getGrantedPermissions().containsAll(PERMISSIONS)

    /** Writes the reading; a record with the same id replaces the old one. */
    suspend fun write(context: Context, weighIn: WeighIn) {
        val client = HealthConnectClient.getOrCreate(context)
        val record = WeightRecord(
            time = weighIn.time,
            zoneOffset = ZoneId.systemDefault().rules.getOffset(weighIn.time),
            weight = Mass.kilograms(weighIn.kilograms),
            metadata = Metadata.activelyRecorded(
                device = Device(type = Device.TYPE_SCALE, manufacturer = "Fitbit", model = "Aria Air"),
                clientRecordId = weighIn.recordId,
            ),
        )
        client.insertRecords(listOf(record))
    }
}
