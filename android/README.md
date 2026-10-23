# Aria Health Bridge (Android)

A small app that listens on MQTT for weigh-ins and saves them to **Health Connect**
(so Google Fit, Fitbit, Samsung Health and others can read them).

```
Aria Air --BLE--> Home Assistant --MQTT--> this app --> Health Connect
```

## Message format

Publish JSON to the topic (default `aria_air/weigh_in`), QoS 1, **not retained**:

```json
{"value": 72.4, "unit": "lb", "time": "2026-10-22T07:30:00+00:00"}
```

- `value` required. `unit` is `kg` (default) or `lb`. `time` is ISO-8601 and defaults to now.
- Each reading gets an id from its time, so a repeated message replaces the first
  instead of adding a second record.
- Readings under 2 kg or over 635 kg are ignored.

## Home Assistant automation

Adjust the entity ids if yours differ. Create it under Settings, Automations.

```yaml
alias: Aria Air weigh-in to MQTT
triggers:
  - trigger: state
    entity_id: sensor.aria_air_473d_last_weigh_in
conditions:
  - "{{ trigger.to_state.state not in ['unknown', 'unavailable'] }}"
actions:
  - action: mqtt.publish
    data:
      topic: aria_air/weigh_in
      qos: 1
      retain: false
      payload: >-
        {{ {'value': states('sensor.aria_air_473d_weight') | float,
            'unit': state_attr('sensor.aria_air_473d_weight', 'unit_of_measurement'),
            'time': trigger.to_state.state} | tojson }}
```

The unit comes from the sensor, so it follows whatever you chose in the integration.

## Build and install

Needs Java 17+ and the Android SDK (API 36).

```bash
cd android
./gradlew testDebugUnitTest assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Using it

1. Open the app (it follows the system light/dark theme) and enter your broker address, port, and the username and password of
   an MQTT user (the same one Home Assistant uses is fine).
2. Choose metric or imperial. This sets how weights are shown in the app and the unit assumed when a message has no `unit`. Health Connect always stores kilograms.
3. Tap **Allow saving weight to Health Connect** and accept.
4. Tap **Save and start**. A quiet notification shows it is connected.
5. Weigh in. The app shows "Saved 72.4 kg ..." and the reading appears in Health Connect.

It connects with a persistent session, so readings made while the phone is offline
arrive when it reconnects. The broker login is stored unencrypted in the app's private
storage, and the connection is plain MQTT (no TLS), so use it on your home network or
over a VPN.
