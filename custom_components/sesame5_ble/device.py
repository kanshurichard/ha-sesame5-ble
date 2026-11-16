"""Sesame 5 BLE Device — connection, OS3 authentication, and lock/unlock operations."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import async_ble_device_from_address

from .const import (
    COMMAND_TIMEOUT,
    CONNECT_TIMEOUT,
    DEFAULT_HISTORY_TAG,
    INITIAL_TOKEN_TIMEOUT,
    LOGIN_TIMEOUT,
    RX_UUID,
    SERVICE_UUID,
    TOUCH_MODELS,
    TX_UUID,
    ItemCode,
    OpCode,
    ResultCode,
)
from .crypto import OS3Cipher, generate_session_key
from .helpers import (
    BleFrameReceiver,
    BleFrameTransmitter,
    Sesame5HistoryRecord,
    Sesame5MechSetting,
    Sesame5MechStatus,
    create_history_tag,
    format_passcode_add_payload,
    format_passcode_delete_payload,
    parse_credential_records,
    parse_passcode_records,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

LOGGER = logging.getLogger(__name__)

STATE_DISCONNECTED = "disconnected"
STATE_CONNECTING = "connecting"
STATE_LOGIN = "login"
STATE_READY = "ready"


class Sesame5Device:
    """Manages BLE connection, SesameOS 3 cryptographic handshake, and commands."""

    def __init__(
        self,
        address: str,
        secret_key: bytes,
        hass: HomeAssistant,
        history_tag: str = DEFAULT_HISTORY_TAG,
        model_id: int | None = None,
    ) -> None:
        self._address = address
        self._secret_key = secret_key
        self._hass = hass
        self._history_tag = history_tag
        self._model_id = model_id

        self._client: BleakClient | None = None
        self._tx_char: BleakGATTCharacteristic | None = None
        self._cipher: OS3Cipher | None = None
        self._session_token: bytes | None = None

        self._rx_buffer = BleFrameReceiver()
        self._mech_status: Sesame5MechStatus | None = None
        self._mech_settings: Sesame5MechSetting | None = None
        self._history: Sesame5HistoryRecord | None = None
        self._door_open: bool | None = None
        self._passcodes: list[dict[str, Any]] = []
        self._fingerprints: list[dict[str, Any]] = []
        self._cards: list[dict[str, Any]] = []

        self._state = STATE_DISCONNECTED
        self._callbacks: list[Callable[[], None]] = []
        self._lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._is_notifying = False
        self._decrypt_failure_count = 0
        self._history_in_progress = False

        self._initial_token_received = asyncio.Event()
        self._logged_in = asyncio.Event()
        self._passcodes_received = asyncio.Event()
        self._fingerprints_received = asyncio.Event()
        self._cards_received = asyncio.Event()
        self._command_response_futures: dict[int, asyncio.Future[tuple[ResultCode, bytes]]] = {}

    @property
    def address(self) -> str:
        return self._address

    @property
    def model_id(self) -> int | None:
        return self._model_id

    @property
    def is_keypad(self) -> bool:
        if self._model_id is not None and self._model_id in TOUCH_MODELS:
            return True
        return False

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def is_ready(self) -> bool:
        return self._state == STATE_READY and self.is_connected

    @property
    def mech_status(self) -> Sesame5MechStatus | None:
        return self._mech_status

    @property
    def mech_settings(self) -> Sesame5MechSetting | None:
        return self._mech_settings

    @property
    def history(self) -> Sesame5HistoryRecord | None:
        return self._history

    @property
    def passcodes(self) -> list[dict[str, Any]]:
        return list(self._passcodes)

    @property
    def fingerprints(self) -> list[dict[str, Any]]:
        return list(self._fingerprints)

    @property
    def cards(self) -> list[dict[str, Any]]:
        return list(self._cards)

    @property
    def passcode_count(self) -> int:
        return len(self._passcodes)

    @property
    def fingerprint_count(self) -> int:
        return len(self._fingerprints)

    @property
    def card_count(self) -> int:
        return len(self._cards)

    @property
    def door_open(self) -> bool | None:
        """Return True if door is currently open, False if closed, None if unknown."""
        return self._door_open

    def set_door_open(self, is_open: bool | None) -> None:
        """Set current door open/closed status."""
        self._door_open = is_open

    def add_update_callback(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def remove_update_callback(self, callback: Callable[[], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_update(self) -> None:
        def _dispatch() -> None:
            for cb in list(self._callbacks):
                try:
                    cb()
                except Exception:
                    LOGGER.exception("Error in Sesame 5 update callback")

        loop = getattr(self._hass, "loop", None)
        if loop and isinstance(loop, asyncio.AbstractEventLoop) and loop.is_running():
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is loop:
                _dispatch()
            else:
                loop.call_soon_threadsafe(_dispatch)
        else:
            _dispatch()

    async def connect(self) -> None:
        """Establish BLE connection and subscribe to notifications."""
        async with self._connect_lock:
            if self.is_connected and self._session_token is not None:
                return

            self._state = STATE_CONNECTING
            self._initial_token_received.clear()
            self._logged_in.clear()
            self._session_token = None
            self._cipher = None
            self._rx_buffer = BleFrameReceiver()
            self._decrypt_failure_count = 0

            LOGGER.debug("[%s] Connecting to Sesame 5 BLE", self._address)
            ble_device = async_ble_device_from_address(self._hass, self._address, connectable=True)

            self._client = await establish_connection(
                BleakClient,
                ble_device or self._address,
                self._address,
                disconnected_callback=self._on_disconnect,
                max_attempts=3,
            )

            LOGGER.debug("[%s] Connected to GATT server, discovering services", self._address)
            for service in self._client.services:
                if service.uuid.lower() == SERVICE_UUID.lower():
                    self._tx_char = service.get_characteristic(TX_UUID)
                    rx_char = service.get_characteristic(RX_UUID)
                    if not self._tx_char or not rx_char:
                        raise RuntimeError("Missing Sesame TX/RX characteristic")

                    if not self._is_notifying:
                        await self._client.start_notify(rx_char, self._on_notify)
                        self._is_notifying = True
                        LOGGER.debug("[%s] Subscribed to RX characteristic", self._address)
                    break
            else:
                raise RuntimeError(f"Sesame service {SERVICE_UUID} not found on device")

            # Wait for the lock to publish its 4-byte session token
            LOGGER.debug("[%s] Waiting for INITIAL session token from device", self._address)
            try:
                await asyncio.wait_for(
                    self._initial_token_received.wait(),
                    timeout=INITIAL_TOKEN_TIMEOUT,
                )
            except asyncio.TimeoutError as err:
                LOGGER.error("[%s] Timed out waiting for INITIAL token", self._address)
                await self.disconnect()
                raise TimeoutError("Sesame 5 INITIAL session token timeout") from err

    def _on_disconnect(self, client: BleakClient) -> None:
        LOGGER.debug("[%s] BLE transport disconnected", self._address)
        self._state = STATE_DISCONNECTED
        self._logged_in.clear()
        self._initial_token_received.clear()
        self._cipher = None
        self._session_token = None
        self._is_notifying = False
        self._client = None
        self._rx_buffer = BleFrameReceiver()
        self._decrypt_failure_count = 0
        self._history_in_progress = False

        # Cancel any pending command futures
        for fut in self._command_response_futures.values():
            if not fut.done():
                fut.cancel()
        self._command_response_futures.clear()

        self._notify_update()

    async def _transmit(self, data: bytes, is_encrypted: bool) -> None:
        """Send chunked data packets over TX characteristic."""
        if not self._client or not self._tx_char:
            raise RuntimeError("Device not connected")

        transmitter = BleFrameTransmitter(data, is_encrypted=is_encrypted)
        chunk = transmitter.get_chunk()
        while chunk is not None:
            await self._client.write_gatt_char(self._tx_char, chunk, response=False)
            chunk = transmitter.get_chunk()

    async def authenticate(self) -> None:
        """Perform SesameOS 3 login authentication handshake."""
        async with self._lock:
            if self.is_ready:
                return

            if not self.is_connected or self._session_token is None:
                await self.connect()

            if self._session_token is None:
                raise RuntimeError("No session token available for authentication")

            self._state = STATE_LOGIN
            session_key = generate_session_key(self._secret_key, self._session_token)
            self._cipher = OS3Cipher(self._session_token, session_key)

            # In SesameOS 3, login command is: ItemCode.LOGIN (1 byte) + session_key[:4] (4 bytes)
            login_payload = bytes([ItemCode.LOGIN.value]) + session_key[:4]

            LOGGER.debug("[%s] Sending SesameOS 3 LOGIN handshake command", self._address)
            await self._transmit(login_payload, is_encrypted=False)

            try:
                await asyncio.wait_for(self._logged_in.wait(), timeout=LOGIN_TIMEOUT)
            except asyncio.TimeoutError as err:
                LOGGER.error("[%s] Authentication timed out", self._address)
                await self.disconnect()
                raise TimeoutError("Sesame 5 login authentication timeout") from err

            self._state = STATE_READY
            LOGGER.info("[%s] Sesame 5 authenticated successfully", self._address)
            if self.is_keypad:
                await self.request_credentials()
            else:
                asyncio.create_task(self.request_history())

    async def _on_notify(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle incoming GATT notifications from RX characteristic."""
        is_encrypted, raw = self._rx_buffer.feed(bytes(data))
        if raw is None:
            return

        if is_encrypted:
            if self._cipher is None:
                LOGGER.warning("[%s] Received encrypted packet before cipher initialized", self._address)
                return
            try:
                raw = self._cipher.decrypt(raw)
                self._decrypt_failure_count = 0
            except Exception as err:
                self._decrypt_failure_count += 1
                LOGGER.error(
                    "[%s] Decryption failed (consecutive=%d, cnt=%d): %s",
                    self._address,
                    self._decrypt_failure_count,
                    self._cipher._decrypt_counter,
                    err,
                )
                if self._decrypt_failure_count >= 2:
                    LOGGER.warning(
                        "[%s] Multiple consecutive decrypt failures; resetting session to force fresh handshake",
                        self._address,
                    )
                    self._decrypt_failure_count = 0
                    asyncio.create_task(self.disconnect())
                return

        if len(raw) < 2:
            LOGGER.warning("[%s] Dropping too short message: %s", self._address, raw.hex())
            return

        op_code_val = raw[0]
        payload = raw[1:]

        if op_code_val == OpCode.PUBLISH.value:
            item_code_val = payload[0]
            pub_data = payload[1:]
            await self._handle_publish(item_code_val, pub_data)

        elif op_code_val == OpCode.RESPONSE.value:
            if len(payload) < 2:
                return
            item_code_val = payload[0]
            result_code_val = payload[1]
            resp_data = payload[2:]
            await self._handle_response(item_code_val, result_code_val, resp_data)

    async def _handle_publish(self, item_code: int, pub_data: bytes) -> None:
        """Handle async publish notifications from the lock."""
        if item_code == ItemCode.INITIAL.value:
            LOGGER.debug("[%s] Received INITIAL token (%d bytes): %s", self._address, len(pub_data), pub_data.hex())
            self._session_token = pub_data
            self._initial_token_received.set()

        elif item_code == ItemCode.MECH_STATUS.value:
            try:
                prev_locked = self._mech_status.is_locked() if self._mech_status else None
                self._mech_status = Sesame5MechStatus(pub_data)
                curr_locked = self._mech_status.is_locked()
                LOGGER.debug(
                    "[%s] MECH_STATUS: locked=%s, pos=%d, target=%d, batt=%d%% (%.2fV)",
                    self._address,
                    curr_locked,
                    self._mech_status.position,
                    self._mech_status.target_position,
                    self._mech_status.battery_percentage,
                    self._mech_status.battery_voltage,
                )

                is_lock_state_change = (
                    prev_locked is not None
                    and curr_locked is not None
                    and prev_locked != curr_locked
                )

                if self.is_ready and not self.is_keypad and is_lock_state_change:
                    # Defer notification until history is retrieved so HA automations
                    # have accurate last_operation_* attributes at the exact moment state changes.
                    async def _sync_history_and_notify() -> None:
                        try:
                            await asyncio.wait_for(self.request_history(), timeout=1.8)
                        except Exception as err:
                            LOGGER.debug("[%s] History sync timed out or failed: %s", self._address, err)
                            self._notify_update()

                    asyncio.create_task(_sync_history_and_notify())
                else:
                    self._notify_update()
                    if self.is_ready and not self.is_keypad:
                        asyncio.create_task(self.request_history())
            except Exception:
                LOGGER.exception("[%s] Failed to parse MECH_STATUS", self._address)

        elif item_code == ItemCode.MECH_SETTING.value:
            try:
                self._mech_settings = Sesame5MechSetting(pub_data)
                LOGGER.debug(
                    "[%s] MECH_SETTING: lock_pos=%d, unlock_pos=%d, autolock=%ds",
                    self._address,
                    self._mech_settings.lock_position,
                    self._mech_settings.unlock_position,
                    self._mech_settings.auto_lock_duration,
                )
                self._notify_update()
            except Exception:
                LOGGER.exception("[%s] Failed to parse MECH_SETTING", self._address)

        # Passcodes
        elif item_code == ItemCode.SSM_OS3_PASSCODE_FIRST.value:
            LOGGER.debug("[%s] Passcode list reception started", self._address)
            self._passcodes = []
            self._passcodes_received.clear()

        elif item_code == ItemCode.SSM_OS3_PASSCODE_NOTIFY.value:
            records = parse_credential_records(pub_data)
            LOGGER.debug("[%s] Received %d passcode records", self._address, len(records))
            self._passcodes.extend(records)

        elif item_code == ItemCode.SSM_OS3_PASSCODE_LAST.value:
            LOGGER.debug("[%s] Passcode list reception finished (total %d)", self._address, len(self._passcodes))
            self._passcodes_received.set()
            self._notify_update()

        elif item_code == ItemCode.SSM_OS3_PASSCODE_DELETE.value:
            LOGGER.info("[%s] Keypad reported passcode deletion event", self._address)
            self._notify_update()

        # Fingerprints
        elif item_code == ItemCode.FINGERPRINT_FIRST.value:
            LOGGER.debug("[%s] Fingerprint list reception started", self._address)
            self._fingerprints = []
            self._fingerprints_received.clear()

        elif item_code == ItemCode.FINGERPRINT_NOTIFY.value:
            records = parse_credential_records(pub_data)
            LOGGER.debug("[%s] Received %d fingerprint records", self._address, len(records))
            self._fingerprints.extend(records)

        elif item_code == ItemCode.FINGERPRINT_LAST.value:
            LOGGER.debug("[%s] Fingerprint list reception finished (total %d)", self._address, len(self._fingerprints))
            self._fingerprints_received.set()
            self._notify_update()

        elif item_code in (ItemCode.FINGERPRINT_DELETE.value, ItemCode.FINGERPRINT_CHANGE.value):
            LOGGER.info("[%s] Keypad reported fingerprint event (%d)", self._address, item_code)
            self._notify_update()

        # Cards
        elif item_code == ItemCode.CARD_FIRST.value:
            LOGGER.debug("[%s] Card list reception started", self._address)
            self._cards = []
            self._cards_received.clear()

        elif item_code == ItemCode.CARD_NOTIFY.value:
            records = parse_credential_records(pub_data)
            LOGGER.debug("[%s] Received %d card records", self._address, len(records))
            self._cards.extend(records)

        elif item_code == ItemCode.CARD_LAST.value:
            LOGGER.debug("[%s] Card list reception finished (total %d)", self._address, len(self._cards))
            self._cards_received.set()
            self._notify_update()

        elif item_code in (ItemCode.CARD_DELETE.value, ItemCode.CARD_CHANGE.value):
            LOGGER.info("[%s] Keypad reported card event (%d)", self._address, item_code)
            self._notify_update()

    async def _handle_response(self, item_code: int, result_code_val: int, resp_data: bytes) -> None:
        """Handle synchronous command responses from the lock."""
        result_code = ResultCode(result_code_val) if result_code_val in ResultCode._value2member_map_ else ResultCode.UNKNOWN
        LOGGER.debug("[%s] Received RESPONSE for item %s: result=%s", self._address, item_code, result_code.name)

        if item_code == ItemCode.LOGIN.value:
            if result_code == ResultCode.SUCCESS:
                LOGGER.debug("[%s] LOGIN accepted by device", self._address)
                self._logged_in.set()
            else:
                LOGGER.error("[%s] LOGIN rejected with result: %s", self._address, result_code.name)
                self._logged_in.clear()
                self._state = STATE_DISCONNECTED

        elif item_code == ItemCode.HISTORY.value and result_code == ResultCode.SUCCESS:
            if len(resp_data) >= 16:
                try:
                    full_raw = bytes([result_code.value]) + resp_data
                    self._history = Sesame5HistoryRecord(full_raw)
                    if self._history.door_open is not None:
                        self._door_open = self._history.door_open
                    LOGGER.info(
                        "[%s] History update: %s (source=%s, tag=%s, time=%s)",
                        self._address,
                        self._history.description_zh,
                        self._history.source,
                        self._history.tag_name or (self._history.history_tag_type.name if self._history.history_tag_type else ""),
                        self._history.iso_timestamp,
                    )
                    self._notify_update()
                except Exception:
                    LOGGER.exception("[%s] Failed to parse HISTORY record", self._address)

        # Resolve any waiting command future
        if item_code in self._command_response_futures:
            fut = self._command_response_futures.pop(item_code)
            if not fut.done():
                fut.set_result((result_code, resp_data))

    async def send_command(self, item_code: ItemCode, payload: bytes, is_encrypted: bool = True) -> tuple[ResultCode, bytes]:
        """Transmit command and wait for corresponding response."""
        if not self.is_ready:
            raise RuntimeError("Device not ready to receive commands")

        command_bytes = bytes([item_code.value]) + payload
        if is_encrypted:
            if self._cipher is None:
                raise RuntimeError("Cipher not initialized for encrypted command")
            data_to_send = self._cipher.encrypt(command_bytes)
        else:
            data_to_send = command_bytes

        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[ResultCode, bytes]] = loop.create_future()
        self._command_response_futures[item_code.value] = future

        try:
            await self._transmit(data_to_send, is_encrypted=is_encrypted)
            result_code, resp_data = await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
            return result_code, resp_data
        except Exception:
            self._command_response_futures.pop(item_code.value, None)
            raise

    async def lock(self, tag: str | None = None) -> None:
        """Send lock command with history tag."""
        history = create_history_tag(tag or self._history_tag)
        LOGGER.info("[%s] Sending LOCK command (tag: %s)", self._address, tag or self._history_tag)
        result, _ = await self.send_command(ItemCode.LOCK, history, is_encrypted=True)
        if result != ResultCode.SUCCESS:
            raise RuntimeError(f"Lock command failed: {result.name}")

    async def unlock(self, tag: str | None = None) -> None:
        """Send unlock command with history tag."""
        history = create_history_tag(tag or self._history_tag)
        LOGGER.info("[%s] Sending UNLOCK command (tag: %s)", self._address, tag or self._history_tag)
        result, _ = await self.send_command(ItemCode.UNLOCK, history, is_encrypted=True)
        if result != ResultCode.SUCCESS:
            raise RuntimeError(f"Unlock command failed: {result.name}")

    async def toggle(self, tag: str | None = None) -> None:
        """Toggle lock state based on current mechanical position."""
        if self._mech_status is not None and self._mech_status.is_in_lock_range:
            await self.unlock(tag)
        else:
            await self.lock(tag)

    async def request_history(self) -> Sesame5HistoryRecord | None:
        """Fetch latest operation history record from the lock."""
        if not self.is_ready:
            return None
        if self._history_in_progress:
            return None
        self._history_in_progress = True
        try:
            LOGGER.debug("[%s] Requesting latest history record from lock", self._address)
            result, resp_data = await self.send_command(ItemCode.HISTORY, b"\x00", is_encrypted=True)
            if result == ResultCode.SUCCESS and len(resp_data) >= 16:
                full_raw = bytes([result.value]) + resp_data
                self._history = Sesame5HistoryRecord(full_raw)
                if self._history.door_open is not None:
                    self._door_open = self._history.door_open
                self._notify_update()
                return self._history
        except Exception as err:
            LOGGER.debug("[%s] Failed to fetch history record (non-fatal): %s", self._address, err)
        finally:
            self._history_in_progress = False
        return None

    async def add_passcode(self, passcode: str, name: str = "HA") -> None:
        """Add a passcode to the keypad."""
        payload = format_passcode_add_payload(passcode, name)
        LOGGER.info("[%s] Adding passcode '%s' (name: %s)", self._address, passcode, name)
        result, _ = await self.send_command(ItemCode.SSM_OS3_PASSCODE_ADD, payload, is_encrypted=True)
        if result != ResultCode.SUCCESS:
            raise RuntimeError(f"Add passcode failed with result: {result.name}")
        LOGGER.info("[%s] Passcode '%s' added successfully", self._address, passcode)

    async def delete_passcode(self, passcode: str) -> None:
        """Delete a passcode from the keypad."""
        payload = format_passcode_delete_payload(passcode)
        LOGGER.info("[%s] Deleting passcode '%s'", self._address, passcode)
        result, _ = await self.send_command(ItemCode.SSM_OS3_PASSCODE_DELETE, payload, is_encrypted=True)
        if result != ResultCode.SUCCESS:
            raise RuntimeError(f"Delete passcode failed with result: {result.name}")
        LOGGER.info("[%s] Passcode '%s' deleted successfully", self._address, passcode)

    async def request_passcodes(self, timeout: float = 4.0) -> list[dict[str, Any]]:
        """Request and return the list of passcodes registered on the device."""
        if not self.is_ready:
            raise RuntimeError("Device not ready to receive commands")
        self._passcodes = []
        self._passcodes_received.clear()
        LOGGER.debug("[%s] Requesting passcode list from keypad", self._address)
        try:
            await self.send_command(ItemCode.SSM_OS3_PASSCODE_GET, b"", is_encrypted=True)
            try:
                await asyncio.wait_for(self._passcodes_received.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                LOGGER.debug("[%s] Timeout waiting for passcode list, returning current items", self._address)
        except Exception as err:
            LOGGER.debug("[%s] SSM_OS3_PASSCODE_GET error: %s", self._address, err)
        return list(self._passcodes)

    async def request_fingerprints(self, timeout: float = 4.0) -> list[dict[str, Any]]:
        """Request and return the list of fingerprints registered on the keypad."""
        if not self.is_ready:
            raise RuntimeError("Device not ready to receive commands")
        self._fingerprints = []
        self._fingerprints_received.clear()
        LOGGER.debug("[%s] Requesting fingerprint list from keypad", self._address)
        try:
            await self.send_command(ItemCode.FINGERPRINT_GET, b"", is_encrypted=True)
            try:
                await asyncio.wait_for(self._fingerprints_received.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                LOGGER.debug("[%s] Timeout waiting for fingerprint list, returning current items", self._address)
        except Exception as err:
            LOGGER.debug("[%s] FINGERPRINT_GET error: %s", self._address, err)
        return list(self._fingerprints)

    async def request_cards(self, timeout: float = 4.0) -> list[dict[str, Any]]:
        """Request and return the list of cards registered on the keypad."""
        if not self.is_ready:
            raise RuntimeError("Device not ready to receive commands")
        self._cards = []
        self._cards_received.clear()
        LOGGER.debug("[%s] Requesting card list from keypad", self._address)
        try:
            await self.send_command(ItemCode.CARD_GET, b"", is_encrypted=True)
            try:
                await asyncio.wait_for(self._cards_received.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                LOGGER.debug("[%s] Timeout waiting for card list, returning current items", self._address)
        except Exception as err:
            LOGGER.debug("[%s] CARD_GET error: %s", self._address, err)
        return list(self._cards)

    async def request_credentials(self, timeout: float = 4.0) -> None:
        """Query passcodes, fingerprints, and cards from keypad."""
        if not self.is_ready or not self.is_keypad:
            return

        LOGGER.debug("[%s] Refreshing all credentials from keypad", self._address)
        try:
            await self.request_passcodes(timeout=timeout)
        except Exception as err:
            LOGGER.debug("[%s] Failed to fetch passcodes: %s", self._address, err)

        try:
            await self.request_fingerprints(timeout=timeout)
        except Exception as err:
            LOGGER.debug("[%s] Failed to fetch fingerprints: %s", self._address, err)

        try:
            await self.request_cards(timeout=timeout)
        except Exception as err:
            LOGGER.debug("[%s] Failed to fetch cards: %s", self._address, err)

        LOGGER.info(
            "[%s] Keypad credentials loaded: %d passcode(s), %d fingerprint(s), %d card(s)",
            self._address,
            len(self._passcodes),
            len(self._fingerprints),
            len(self._cards),
        )
        self._notify_update()

    async def disconnect(self) -> None:
        """Disconnect GATT client gracefully."""
        if self._client and self._client.is_connected:
            if self._is_notifying:
                try:
                    await self._client.stop_notify(RX_UUID)
                except Exception:
                    pass
                self._is_notifying = False
            try:
                await self._client.disconnect()
            except Exception:
                pass

        self._state = STATE_DISCONNECTED
        self._logged_in.clear()
        self._initial_token_received.clear()
        self._cipher = None
        self._session_token = None
        self._is_notifying = False
        self._client = None
        self._rx_buffer = BleFrameReceiver()
        self._decrypt_failure_count = 0
        self._history_in_progress = False
        LOGGER.debug("[%s] Disconnected cleanly", self._address)
