"""Protocol helpers: status parsing, packet framing, QR decoding, and device info."""

from __future__ import annotations

import base64
import struct
import urllib.parse
from uuid import UUID
from typing import TYPE_CHECKING, Any

from .const import (
    BATTERY_PERCENTAGES,
    DOMAIN,
    ItemCode,
    MechStatusBitFlag,
    OpCode,
    PacketType,
    PRODUCT_NAMES,
    ResultCode,
    VOLTAGE_LEVELS,
)

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice
    from homeassistant.config_entries import ConfigEntry
    from .coordinator import Sesame5Coordinator


def calculate_battery_percentage(voltage: float) -> int:
    """Calculate battery percentage from voltage using Sesame interpolation table."""
    if voltage >= VOLTAGE_LEVELS[0]:
        return int(BATTERY_PERCENTAGES[0])
    if voltage <= VOLTAGE_LEVELS[-1]:
        return int(BATTERY_PERCENTAGES[-1])

    for i in range(len(VOLTAGE_LEVELS) - 1):
        v_upper = VOLTAGE_LEVELS[i]
        v_lower = VOLTAGE_LEVELS[i + 1]
        if v_lower < voltage <= v_upper:
            ratio = (voltage - v_lower) / (v_upper - v_lower)
            p_upper = BATTERY_PERCENTAGES[i]
            p_lower = BATTERY_PERCENTAGES[i + 1]
            return int((p_upper - p_lower) * ratio + p_lower)

    return 0


def create_history_tag(tag: str, max_len: int = 20) -> bytes:
    """Create a length-prefixed UTF-8 history tag payload.

    Args:
        tag: String to record in Sesame history.
        max_len: Max bytes allowed (Sesame standard is 20).

    Returns:
        1 byte length + UTF-8 encoded string bytes.
    """
    raw = tag.encode("utf-8")[:max_len].decode("utf-8", errors="ignore").encode("utf-8")
    return bytes([len(raw)]) + raw


def parse_secret_key_input(input_str: str) -> tuple[bytes, str | None, int | None]:
    """Parse user-provided secret key input.

    Supports:
    1. Full Sesame QR code URL: `ssm://UI?t=sk&sk=...&l=0&n=...`
    2. Base64 encoded shared key string (39 bytes binary)
    3. Raw 32-character hex secret key

    Returns:
        tuple of (secret_key_bytes, device_uuid_string or None, product_model_id or None)
    """
    clean_str = input_str.strip()

    # Case 1: Sesame App QR code URL
    if clean_str.startswith("ssm://") or "sk=" in clean_str:
        parsed_url = urllib.parse.urlparse(clean_str)
        qs = urllib.parse.parse_qs(parsed_url.query)
        sk_b64 = qs.get("sk", [""])[0]
        if not sk_b64:
            raise ValueError("No 'sk' parameter found in QR code URL")
        clean_str = sk_b64

    # Case 2: Hex string (32 characters = 16 bytes)
    if len(clean_str) == 32:
        try:
            return bytes.fromhex(clean_str), None, None
        except ValueError:
            pass

    # Case 3: Base64 string
    try:
        raw_bytes = base64.b64decode(clean_str)
    except Exception as exc:
        raise ValueError(f"Failed to decode base64 key: {exc}") from exc

    # SesameOS 3 QR shared key format: >B16s4s2s16s (39 bytes)
    if len(raw_bytes) == 39:
        model_id, secret_key, _, _, uuid_bytes = struct.unpack(">B16s4s2s16s", raw_bytes)
        device_uuid = str(UUID(bytes=uuid_bytes))
        return secret_key, device_uuid, model_id

    # Raw 16-byte secret key in base64
    if len(raw_bytes) == 16:
        return raw_bytes, None, None

    # Legacy SesameOS 2 format (>99 bytes): fallback to extracting 16-byte secret key
    if len(raw_bytes) >= 99:
        secret_key = raw_bytes[1:17]
        return secret_key, None, None

    raise ValueError(
        f"Unrecognized key format: length {len(raw_bytes)} bytes. Expected 16-byte hex, "
        "39-byte SesameOS 3 QR code, or Sesame QR URL."
    )


class Sesame5MechStatus:
    """Parsed mechanical status of a Sesame 5 / SesameOS 3 lock."""

    def __init__(self, payload: bytes) -> None:
        if len(payload) < 7:
            raise ValueError(f"MechStatus payload too short: {len(payload)} bytes, expected 7")

        raw_battery, target, position, status_flags = struct.unpack("<HhhB", payload[:7])
        self._raw_battery = raw_battery
        self._target = target
        self._position = position
        self._flags = status_flags

        self._battery_voltage = raw_battery * 2 / 1000.0
        self._battery_pct = calculate_battery_percentage(self._battery_voltage)

    @property
    def battery_voltage(self) -> float:
        return round(self._battery_voltage, 2)

    @property
    def battery_percentage(self) -> int:
        return self._battery_pct

    @property
    def target_position(self) -> int:
        return self._target

    @property
    def position(self) -> int:
        return self._position

    @property
    def is_in_lock_range(self) -> bool:
        return bool(self._flags & MechStatusBitFlag.IS_IN_LOCK_RANGE)

    @property
    def is_in_unlock_range(self) -> bool:
        return bool(self._flags & MechStatusBitFlag.IS_IN_UNLOCK_RANGE)

    @property
    def is_stop(self) -> bool:
        return bool(self._flags & MechStatusBitFlag.IS_STOP)

    @property
    def is_battery_critical(self) -> bool:
        return bool(self._flags & MechStatusBitFlag.IS_BATTERY_CRITICAL)

    @property
    def is_clutch_failed(self) -> bool:
        return bool(self._flags & MechStatusBitFlag.IS_CLUTCH_FAILED)

    def is_locked(self) -> bool | None:
        """Return True if locked, False if unlocked, None if undetermined/moving."""
        if self.is_in_lock_range:
            return True
        if self.is_in_unlock_range:
            return False
        return None


class Sesame5MechSetting:
    """Parsed mechanical settings for Sesame 5 lock."""

    def __init__(self, payload: bytes) -> None:
        if len(payload) < 6:
            raise ValueError(f"MechSetting payload too short: {len(payload)} bytes, expected 6")

        lock_pos, unlock_pos, auto_lock = struct.unpack("<hhH", payload[:6])
        self.lock_position = lock_pos
        self.unlock_position = unlock_pos
        self.auto_lock_duration = auto_lock

    @property
    def is_configured(self) -> bool:
        return self.lock_position != self.unlock_position


class Sesame5Advertisement:
    """Parsed Sesame 5 BLE advertisement manufacturer data."""

    def __init__(self, dev: BLEDevice, mfg_data: dict[int, bytes]) -> None:
        self.address = dev.address
        self.device = dev
        self.name = dev.name or ""
        self.device_uuid: UUID | None = None
        self.model_id: int | None = None
        self.is_registered: bool = False

        data = next(iter(mfg_data.values())) if mfg_data else b""
        if len(data) >= 19:
            try:
                model_val, reg_val, uuid_bytes = struct.unpack("<HB16s", data[:19])
                self.model_id = model_val
                self.is_registered = bool(reg_val)
                self.device_uuid = UUID(bytes=uuid_bytes)
            except Exception:
                pass

    @property
    def model_name(self) -> str:
        if self.model_id in PRODUCT_NAMES:
            return PRODUCT_NAMES[self.model_id]
        return f"Sesame Device (Type {self.model_id})" if self.model_id else "Sesame 5"


class BleFrameTransmitter:
    """Splits an outgoing BLE message into MTU-sized packets with 1-byte headers."""

    MTU = 19  # Standard BLE payload chunk (20 bytes total - 1 byte header)

    def __init__(self, data: bytes, is_encrypted: bool) -> None:
        self._is_encrypted = is_encrypted
        self._chunks = [data[i : i + self.MTU] for i in range(0, len(data), self.MTU)]
        self._is_first = True

    def get_chunk(self) -> bytes | None:
        if not self._chunks:
            return None

        chunk = self._chunks.pop(0)
        is_end = len(self._chunks) == 0

        header = 0
        if self._is_first:
            header |= PacketType.BEGINNING
            self._is_first = False

        if is_end:
            header |= PacketType.ENCRYPTED_END if self._is_encrypted else PacketType.PLAINTEXT_END

        return bytes([header]) + chunk


class BleFrameReceiver:
    """Reassembles fragmented BLE notification packets into a single message."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, packet: bytes) -> tuple[bool | None, bytes | None]:
        """Process incoming packet chunk.

        Returns:
            (is_encrypted, payload_bytes) when message is complete, or (None, None) if incomplete.
        """
        if not packet:
            return None, None

        header = packet[0]
        data = packet[1:]

        is_beginning = bool(header & PacketType.BEGINNING)
        is_plaintext_end = bool(header & PacketType.PLAINTEXT_END)
        is_encrypted_end = bool(header & PacketType.ENCRYPTED_END)

        if is_beginning:
            self._buffer = bytearray(data)
        else:
            self._buffer.extend(data)

        if is_encrypted_end:
            full_data = bytes(self._buffer)
            self._buffer.clear()
            return True, full_data

        if is_plaintext_end:
            full_data = bytes(self._buffer)
            self._buffer.clear()
            return False, full_data

        return None, None


def get_device_info(coordinator: Sesame5Coordinator, entry: ConfigEntry) -> Any:
    """Generate DeviceInfo for Home Assistant device registry."""
    from homeassistant.helpers.device_registry import DeviceInfo

    model_name = entry.data.get("model", "Sesame 5")
    device_id = entry.data.get("device_id", coordinator.address)

    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.address)},
        name=f"{model_name} ({coordinator.address[-5:].replace(':', '')})",
        manufacturer="CANDY HOUSE",
        model=model_name,
        serial_number=device_id,
    )
