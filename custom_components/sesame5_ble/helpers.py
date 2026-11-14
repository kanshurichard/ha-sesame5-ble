"""Protocol helpers: status parsing, packet framing, QR decoding, and device info."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import struct
import urllib.parse
from uuid import UUID
from typing import TYPE_CHECKING, Any

from .const import (
    BATTERY_PERCENTAGES,
    DOMAIN,
    HistoryTagType,
    HistoryType,
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
    """Parsed mechanical status of a Sesame 5 / SesameOS 3 lock or Sesame Touch."""

    def __init__(self, payload: bytes) -> None:
        self.raw = payload
        self.card_count: int | None = None
        self.fingerprint_count: int | None = None
        self.password_count: int | None = None

        if len(payload) >= 9:
            # Sesame Touch / Touch Pro / Face MechStatus: <HhhhB (9 bytes)
            (
                raw_battery,
                card_count,
                fp_count,
                pwd_count,
                status_flags,
            ) = struct.unpack("<HhhhB", payload[:9])
            self.card_count = card_count
            self.fingerprint_count = fp_count
            self.password_count = pwd_count
            self._target = 0
            self._position = 0
            self._raw_battery = raw_battery
            self._flags = status_flags
        elif len(payload) >= 7:
            # Sesame 5 / 5 Pro MechStatus: <HhhB (7 bytes)
            raw_battery, target, position, status_flags = struct.unpack("<HhhB", payload[:7])
            self._target = target
            self._position = position
            self._raw_battery = raw_battery
            self._flags = status_flags
        else:
            raise ValueError(f"MechStatus payload too short: {len(payload)} bytes, expected at least 7")

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
        """Return True if locked, False if unlocked, None if undetermined/moving or not a lock."""
        if self.card_count is not None:
            return None
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


class Sesame5HistoryRecord:
    """Parsed operation history record from Sesame lock."""

    def __init__(self, raw_data: bytes) -> None:
        """Parse history response payload.

        Expected format:
        [result_code (1B), record_id (4B), hist_type (1B), timestamp (4B), mecha_status (7B), tag_data...]
        """
        if len(raw_data) < 17:
            raise ValueError(f"History payload too short: {len(raw_data)} bytes, expected at least 17")

        self.result = ResultCode(raw_data[0]) if raw_data[0] in ResultCode._value2member_map_ else ResultCode.UNKNOWN
        self.record_id = int.from_bytes(raw_data[1:5], "little")
        hist_type_val = raw_data[5]
        self.timestamp = int.from_bytes(raw_data[6:10], "little")
        self.mecha_status_raw = raw_data[10:17]

        self.tag_name: str = ""
        self.history_tag_type: HistoryTagType | None = None
        self.accessory_uuid: str | None = None

        tag_data = raw_data[17:]
        if tag_data:
            tag_len = tag_data[0]
            if hist_type_val in (HistoryType.BLE_LOCK.value, HistoryType.BLE_UNLOCK.value):
                if tag_len >= 60:
                    hist_type_val = (
                        HistoryType.WEB_LOCK.value
                        if hist_type_val == HistoryType.BLE_LOCK.value
                        else HistoryType.WEB_UNLOCK.value
                    )
                    tag_len %= 30
                elif tag_len >= 30:
                    hist_type_val = (
                        HistoryType.WM2_LOCK.value
                        if hist_type_val == HistoryType.BLE_LOCK.value
                        else HistoryType.WM2_UNLOCK.value
                    )
                    tag_len %= 30

            tag_len = min(tag_len, 29)
            if tag_len > 0 and len(tag_data) >= 1 + tag_len:
                self.tag_name = tag_data[1 : 1 + tag_len].decode("utf-8", errors="ignore").strip()
            elif len(tag_data) >= 18:
                tag_type_val = tag_data[1]
                if tag_type_val in HistoryTagType._value2member_map_:
                    self.history_tag_type = HistoryTagType(tag_type_val)
                self.accessory_uuid = tag_data[2:18].hex()

        self.history_type = (
            HistoryType(hist_type_val)
            if hist_type_val in HistoryType._value2member_map_
            else HistoryType.NONE
        )

    @property
    def iso_timestamp(self) -> str:
        if self.timestamp <= 0:
            return ""
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()

    @property
    def action(self) -> str:
        """Return 'lock', 'unlock', or 'other'."""
        if self.history_type in (
            HistoryType.BLE_UNLOCK,
            HistoryType.MANUAL_UNLOCKED,
            HistoryType.DRIVE_UNLOCKED,
            HistoryType.WM2_UNLOCK,
            HistoryType.WEB_UNLOCK,
        ):
            return "unlock"
        if self.history_type in (
            HistoryType.BLE_LOCK,
            HistoryType.MANUAL_LOCKED,
            HistoryType.AUTOLOCK,
            HistoryType.DRIVE_LOCKED,
            HistoryType.WM2_LOCK,
            HistoryType.WEB_LOCK,
        ):
            return "lock"
        return "other"

    @property
    def source(self) -> str:
        """Return operation source: inside, outside, auto, remote, app."""
        if self.history_type in (HistoryType.MANUAL_LOCKED, HistoryType.MANUAL_UNLOCKED, HistoryType.MANUAL_ELSE):
            return "inside"
        if self.history_type == HistoryType.AUTOLOCK:
            return "auto"
        if self.history_tag_type in (
            HistoryTagType.FINGERPRINT,
            HistoryTagType.PASSWORD,
            HistoryTagType.NFC_CARD,
            HistoryTagType.FACE,
            HistoryTagType.PALM_VEIN,
            HistoryTagType.TOUCH_LOCK,
            HistoryTagType.TOUCH_PRO_LOCK,
        ):
            return "outside"
        if self.history_tag_type in (HistoryTagType.REMOTE, HistoryTagType.REMOTE_NANO):
            return "remote"
        if self.history_type in (
            HistoryType.WM2_LOCK,
            HistoryType.WM2_UNLOCK,
            HistoryType.WEB_LOCK,
            HistoryType.WEB_UNLOCK,
        ):
            return "remote"
        if self.history_type in (HistoryType.BLE_LOCK, HistoryType.BLE_UNLOCK):
            return "app"
        return "unknown"

    @property
    def description_zh(self) -> str:
        """Human-readable description in Chinese."""
        if self.history_type == HistoryType.MANUAL_UNLOCKED:
            return "门内手动解锁"
        if self.history_type == HistoryType.MANUAL_LOCKED:
            return "门内手动上锁"
        if self.history_type == HistoryType.MANUAL_ELSE:
            return "门内手动旋转"

        if self.history_type == HistoryType.AUTOLOCK:
            return "自动上锁"

        if self.history_tag_type == HistoryTagType.FINGERPRINT:
            return "门外指纹解锁"
        if self.history_tag_type == HistoryTagType.PASSWORD:
            return "门外密码解锁"
        if self.history_tag_type == HistoryTagType.NFC_CARD:
            return "门外卡片解锁 (NFC)"
        if self.history_tag_type == HistoryTagType.FACE:
            return "门外面部识别解锁"
        if self.history_tag_type == HistoryTagType.PALM_VEIN:
            return "门外掌静脉解锁"
        if self.history_tag_type in (HistoryTagType.TOUCH_LOCK, HistoryTagType.TOUCH_PRO_LOCK):
            return "门外按键上锁 (Touch)"
        if self.history_tag_type in (HistoryTagType.REMOTE, HistoryTagType.REMOTE_NANO):
            return "遥控器解锁" if self.action == "unlock" else "遥控器上锁"
        if self.history_tag_type == HistoryTagType.OPEN_SENSOR:
            return "门磁联动开闭"

        if self.history_type == HistoryType.WM2_UNLOCK:
            return "Wi-Fi 网关远程解锁"
        if self.history_type == HistoryType.WM2_LOCK:
            return "Wi-Fi 网关远程上锁"
        if self.history_type == HistoryType.WEB_UNLOCK:
            return "云端 Web API 解锁"
        if self.history_type == HistoryType.WEB_LOCK:
            return "云端 Web API 上锁"

        if self.history_type == HistoryType.BLE_UNLOCK:
            tag = f" ({self.tag_name})" if self.tag_name else ""
            return f"蓝牙/App 解锁{tag}"
        if self.history_type == HistoryType.BLE_LOCK:
            tag = f" ({self.tag_name})" if self.tag_name else ""
            return f"蓝牙/App 上锁{tag}"

        if self.action == "unlock":
            return "已解锁"
        if self.action == "lock":
            return "已上锁"
        return "未知操作"


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


def format_passcode_add_payload(passcode: str, name: str = "HA") -> bytes:
    """Format SSM_OS3_PASSCODE_ADD payload (36 bytes).

    Layout:
    [0xF0, 0x00, id_len] + id_bytes (16B padded) + [name_len] + name_bytes (16B padded)
    """
    clean_code = str(passcode).strip()
    if not clean_code.isdigit():
        raise ValueError(f"Passcode must contain only digits: {passcode}")
    if not (4 <= len(clean_code) <= 16):
        raise ValueError(f"Passcode length must be between 4 and 16 digits, got {len(clean_code)}")

    # Convert each digit character to single integer byte 0..9
    id_bytes = bytes([int(c) for c in clean_code])
    name_bytes = name.encode("utf-8")[:16]

    header = bytes([0xF0, 0x00, len(id_bytes)])
    id_padded = id_bytes.ljust(16, b"\x00")
    name_len = bytes([len(name_bytes)])
    name_padded = name_bytes.ljust(16, b"\x00")

    return header + id_padded + name_len + name_padded


def format_passcode_delete_payload(passcode: str) -> bytes:
    """Format SSM_OS3_PASSCODE_DELETE payload.

    Accepts PIN digits string (e.g. '1234') or hex string of PIN bytes (e.g. '01020304').
    """
    clean = str(passcode).strip()
    # Check if it is a formatted hex ID where each 2 hex chars represents a digit (e.g. '01020304')
    if len(clean) >= 8 and len(clean) % 2 == 0 and all(clean[i] == "0" for i in range(0, len(clean), 2)):
        return bytes.fromhex(clean)
    if clean.isdigit():
        return bytes([int(c) for c in clean])
    try:
        return bytes.fromhex(clean)
    except ValueError:
        raise ValueError(f"Invalid passcode format: {passcode}")


def parse_passcode_records(payload: bytes) -> list[dict[str, Any]]:
    """Parse SSM_OS3_PASSCODE_NOTIFY records.

    Record layout:
    [cardType(1B), idLen(1B), id(idLen B), nameLen(1B), name(nameLen B)]
    """
    records: list[dict[str, Any]] = []
    rest = payload
    while len(rest) >= 4:
        try:
            card_type = rest[0]
            id_len = rest[1]
            if len(rest) < 2 + id_len + 1:
                break
            id_bytes = rest[2 : 2 + id_len]
            name_len = rest[2 + id_len]
            if len(rest) < 2 + id_len + 1 + name_len:
                break
            name_bytes = rest[3 + id_len : 3 + id_len + name_len]

            # Format PIN string from digit bytes if all bytes <= 9
            if all(b <= 9 for b in id_bytes):
                pin_str = "".join(str(b) for b in id_bytes)
            else:
                pin_str = id_bytes.hex()
            name_str = name_bytes.decode("utf-8", errors="ignore").strip()

            records.append(
                {
                    "type": card_type,
                    "passcode": pin_str,
                    "passcode_id": id_bytes.hex(),
                    "name": name_str,
                }
            )
            record_size = 1 + 1 + id_len + 1 + name_len
            if record_size <= 0:
                break
            rest = rest[record_size:]
        except Exception:
            break
    return records
