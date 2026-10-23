"""Bluetooth logic for the Fitbit Aria Air.

The scale is event driven: it only accepts a connection while someone stands on
it, and it reports each weigh-in once before going back to sleep. So instead of
polling, we watch its advertisements and open a short connection when it wakes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import time

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.util.dt as dt_util

from .const import (
    ALWAYS_CONNECT_COOLDOWN,
    CCCD_NOTIFY,
    CCCD_UUID,
    CONF_ALWAYS_CONNECT,
    CONF_KEY,
    CONF_UNIT,
    CONNECT_MAX,
    DISCONNECT_MAX,
    DOMAIN,
    IDLE_AFTER_READING,
    MANUFACTURER_ID,
    NO_DATA_TIMEOUT,
    RETRY_COOLDOWN,
    SESSION_MAX,
    WEIGHT_CHAR_UUID,
)
from .decode import DecodeError, WeighIn, decode_weigh_in, parse_key

_LOGGER = logging.getLogger(__name__)


class AriaAirCoordinator:
    """Watch one scale, read its weigh-ins and tell the entities about them."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Set up state; nothing is started until ``async_start``."""
        self.hass = hass
        self.entry = entry
        self.address: str = entry.data[CONF_ADDRESS]
        self._key = parse_key(entry.data[CONF_KEY])

        self.weight: float | None = None
        self.unit_flag: int | None = None
        self.last_weigh_in: datetime | None = None
        self.in_use: bool | None = None
        self.status = "Idle"
        self.sessions = 0
        self.failed_sessions = 0
        self.readings = 0

        self._listeners: set[Callable[[], None]] = set()
        self._session: asyncio.Task[None] | None = None
        self._last_session_end = 0.0
        self._last_data = 0.0
        self._warned_decode = False

    # --- configuration -------------------------------------------------

    @property
    def unit(self) -> str:
        """Unit the scale reports in, as chosen by the user."""
        return self.entry.options.get(CONF_UNIT, self.entry.data[CONF_UNIT])

    @property
    def always_connect(self) -> bool:
        """Whether to try connecting on every advertisement."""
        return self.entry.options.get(CONF_ALWAYS_CONNECT, False)

    @property
    def session_running(self) -> bool:
        """Whether a connection session is currently open."""
        return self._session is not None and not self._session.done()

    # --- entity plumbing -----------------------------------------------

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        """Register an entity callback; returns the remover."""
        self._listeners.add(update)
        return lambda: self._listeners.discard(update)

    @callback
    def _async_set_status(self, status: str) -> None:
        """Record what the connection is doing, for the diagnostic sensor."""
        if status != self.status:
            self.status = status
            self._async_notify()

    @callback
    def _async_notify(self) -> None:
        for update in list(self._listeners):
            update()

    # --- lifecycle ------------------------------------------------------

    @callback
    def async_start(self) -> Callable[[], None]:
        """Start watching advertisements; returns a function that stops everything."""
        cancel = bluetooth.async_register_callback(
            self.hass,
            self._async_on_advertisement,
            BluetoothCallbackMatcher(address=self.address, connectable=True),
            BluetoothScanningMode.ACTIVE,
        )
        cancel_timer = async_track_time_interval(
            self.hass,
            self._async_on_timer,
            timedelta(seconds=ALWAYS_CONNECT_COOLDOWN),
        )

        @callback
        def _stop() -> None:
            cancel()
            cancel_timer()
            if self._session and not self._session.done():
                self._session.cancel()

        return _stop

    # --- advertisements -------------------------------------------------

    @callback
    def _async_on_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        data = service_info.manufacturer_data.get(MANUFACTURER_ID)
        in_use = bool(data and len(data) >= 2 and data[1])
        _LOGGER.debug(
            "%s: advertisement from %s, manufacturer data %s, in use: %s",
            self.address,
            service_info.source,
            data.hex() if data else None,
            in_use,
        )
        self.in_use = in_use
        if in_use:
            self._async_start_session(service_info.device)

    @callback
    def _async_on_timer(self, _now: datetime) -> None:
        """Try on a schedule, as Home Assistant only delivers changed advertisements.

        An idle scale repeats the same advertisement, so waiting for one would
        leave a scale that is awake but not reporting it unvisited.
        """
        if not self.always_connect:
            return
        device = self._async_get_device()
        if device is not None:
            self._async_start_session(device)

    @callback
    def _async_start_session(self, device: BLEDevice) -> None:
        """Start a session unless one is open or one has just ended."""
        if self.session_running:
            return
        if time.monotonic() - self._last_session_end < RETRY_COOLDOWN:
            return
        _LOGGER.debug("%s: starting a session", self.address)
        self._session = self.entry.async_create_background_task(
            self.hass,
            self._async_run_sessions(device),
            name=f"{DOMAIN} session {self.address}",
        )

    # --- sessions -------------------------------------------------------

    def _async_get_device(self) -> BLEDevice | None:
        return bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )

    async def _async_run_sessions(self, device: BLEDevice) -> None:
        """Run sessions until a weigh-in arrives or the scale goes back to sleep.

        Advertisements only reach us when their contents change, so without this
        a failed session would not be retried while the scale stays awake.
        """
        while True:
            self.sessions += 1
            if await self._async_run_session(device) or not self.in_use:
                return
            await asyncio.sleep(RETRY_COOLDOWN)
            _LOGGER.debug("%s: scale is still awake, retrying", self.address)

    async def _async_run_session(self, device: BLEDevice) -> bool:
        """Connect, subscribe, collect weigh-ins, disconnect.

        Returns whether a weigh-in arrived.
        """
        loop = asyncio.get_running_loop()
        disconnected = asyncio.Event()
        client: BleakClient | None = None
        readings = self.readings
        try:
            self._async_set_status("Connecting")
            async with asyncio.timeout(CONNECT_MAX):
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    device,
                    self.entry.title,
                    disconnected_callback=lambda _client: disconnected.set(),
                    max_attempts=6,
                    ble_device_callback=lambda: self._async_get_device() or device,
                )
                self._async_set_status("Connected, waiting for a weigh-in")
                await self._async_subscribe(client)

            started = self._last_data = loop.time()
            got_reading = False
            while not disconnected.is_set():
                await asyncio.sleep(1)
                now = loop.time()
                got_reading = got_reading or self._last_data > started
                idle = now - self._last_data
                if now - started > SESSION_MAX:
                    break
                if got_reading and idle > IDLE_AFTER_READING:
                    break
                if not got_reading and now - started > NO_DATA_TIMEOUT:
                    _LOGGER.debug("%s: nothing received, closing", self.address)
                    self.failed_sessions += 1
                    self._async_set_status("Connected but no weigh-in arrived")
                    break
        except asyncio.CancelledError:
            raise
        except (BleakError, TimeoutError, OSError) as err:
            _LOGGER.debug("%s: session ended: %s", self.address, err)
            self.failed_sessions += 1
            self._async_set_status(f"Could not connect: {type(err).__name__}")
        finally:
            if client is not None:
                try:
                    async with asyncio.timeout(DISCONNECT_MAX):
                        await client.disconnect()
                except (BleakError, TimeoutError, OSError):
                    pass
            self._last_session_end = time.monotonic()
            if self.status in ("Connecting", "Connected, waiting for a weigh-in"):
                self._async_set_status("Idle")
        return self.readings > readings

    async def _async_subscribe(self, client: BleakClient) -> None:
        """Enable weigh-in messages the way the Fitbit app does."""
        char = client.services.get_characteristic(WEIGHT_CHAR_UUID)
        if char is None:
            raise BleakError("weight characteristic not found; is this an Aria Air?")

        await client.start_notify(char, self._handle_indication)

        # The scale only sends once its configuration value is 0x0001, but some
        # Bluetooth backends write 0x0002 for an indicate-only characteristic.
        # Write the value explicitly; where the backend forbids it (BlueZ, and
        # newer Bleak with a ValueError), the default value above is what we get.
        descriptor = char.get_descriptor(CCCD_UUID)
        if descriptor is not None:
            try:
                await client.write_gatt_descriptor(descriptor.handle, CCCD_NOTIFY)
            except (
                BleakError,
                TimeoutError,
                OSError,
                NotImplementedError,
                ValueError,
            ) as err:
                _LOGGER.debug("%s: could not set notify value: %s", self.address, err)

    # --- readings -------------------------------------------------------

    def _handle_indication(self, _char: object, data: bytearray) -> None:
        """Bleak callback; may arrive from another thread, so hop to the loop."""
        try:
            reading = decode_weigh_in(self._key, bytes(data))
        except DecodeError as err:
            level = logging.DEBUG if self._warned_decode else logging.WARNING
            self._warned_decode = True
            _LOGGER.log(level, "%s: ignoring unreadable message (%s)", self.address, err)
            return
        self.hass.loop.call_soon_threadsafe(self._async_apply_reading, reading)

    @callback
    def _async_apply_reading(self, reading: WeighIn) -> None:
        _LOGGER.debug("%s: weigh-in %s", self.address, reading)
        self.readings += 1
        self.weight = reading.value
        self.unit_flag = reading.unit_flag
        self.last_weigh_in = dt_util.utcnow()
        self._last_data = asyncio.get_running_loop().time()
        self.status = "Received a weigh-in"
        self._async_notify()
