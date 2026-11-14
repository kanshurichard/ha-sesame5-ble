"""Unit tests for Sesame Touch / Keypad separation and passcode management."""

import tests  # Preload mock stubs
import asyncio
from datetime import datetime, timezone
import struct
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.sesame5_ble.const import (
    ItemCode,
    MechStatusBitFlag,
    ProductModel,
    ResultCode,
    TOUCH_MODELS,
    LOCK_MODELS,
    SIGNAL_SESAME_HISTORY_UPDATE,
)
from custom_components.sesame5_ble.coordinator import Sesame5Coordinator
from custom_components.sesame5_ble.device import Sesame5Device
from custom_components.sesame5_ble.helpers import (
    HistoryTagType,
    HistoryType,
    Sesame5HistoryRecord,
    Sesame5MechStatus,
    format_passcode_add_payload,
    format_passcode_delete_payload,
    parse_passcode_records,
)


class TestSesameTouch(unittest.IsolatedAsyncioTestCase):
    """Test Sesame Touch mech status and passcode payloads."""

    def test_touch_mech_status_parsing(self):
        """Test parsing of 9-byte Touch mech status (<HhhhB)."""
        # raw_battery=2900 (5.8V), card_count=2, fp_count=3, pwd_count=4, flags=0
        payload = struct.pack("<HhhhB", 2900, 2, 3, 4, 0)
        status = Sesame5MechStatus(payload)

        self.assertEqual(status.card_count, 2)
        self.assertEqual(status.fingerprint_count, 3)
        self.assertEqual(status.password_count, 4)
        self.assertEqual(status.battery_voltage, 5.8)
        self.assertGreater(status.battery_percentage, 80)
        self.assertIsNone(status.is_locked())

    def test_lock_mech_status_parsing(self):
        """Test parsing of 7-byte Lock mech status (<HhhB)."""
        # raw_battery=2900, target=0, position=0, flags=IS_IN_LOCK_RANGE
        payload = struct.pack("<HhhB", 2900, 0, 0, MechStatusBitFlag.IS_IN_LOCK_RANGE)
        status = Sesame5MechStatus(payload)

        self.assertIsNone(status.card_count)
        self.assertIsNone(status.fingerprint_count)
        self.assertIsNone(status.password_count)
        self.assertTrue(status.is_locked())

    def test_format_passcode_add_payload(self):
        """Test formatting of SSM_OS3_PASSCODE_ADD payload."""
        payload = format_passcode_add_payload("1234", "Guest")
        self.assertEqual(len(payload), 36)

        # Header: 0xF0, 0x00, id_len=4
        self.assertEqual(payload[0], 0xF0)
        self.assertEqual(payload[1], 0x00)
        self.assertEqual(payload[2], 4)

        # ID padded to 16 bytes: 0x01, 0x02, 0x03, 0x04 followed by 12 zeros
        expected_id = bytes([1, 2, 3, 4]) + b"\x00" * 12
        self.assertEqual(payload[3:19], expected_id)

        # Name len: 5
        self.assertEqual(payload[19], 5)

        # Name padded to 16 bytes: "Guest" followed by 11 zeros
        expected_name = b"Guest" + b"\x00" * 11
        self.assertEqual(payload[20:36], expected_name)

    def test_format_passcode_add_validation(self):
        """Test validation for invalid passcodes."""
        with self.assertRaises(ValueError):
            format_passcode_add_payload("123")  # too short (< 4)
        with self.assertRaises(ValueError):
            format_passcode_add_payload("12345678901234567")  # too long (> 16)
        with self.assertRaises(ValueError):
            format_passcode_add_payload("abcd")  # non-digit

    def test_format_passcode_delete_payload(self):
        """Test formatting of SSM_OS3_PASSCODE_DELETE payload."""
        # By PIN string
        payload = format_passcode_delete_payload("1234")
        self.assertEqual(payload, bytes([1, 2, 3, 4]))

        # By hex string
        payload_hex = format_passcode_delete_payload("01020304")
        self.assertEqual(payload_hex, bytes([1, 2, 3, 4]))

    def test_parse_passcode_records(self):
        """Test parsing of SSM_OS3_PASSCODE_NOTIFY record stream."""
        # Record 1: type=0, idLen=4, id=[1,2,3,4], nameLen=4, name="Test"
        rec1 = bytes([0, 4, 1, 2, 3, 4, 4]) + b"Test"
        records = parse_passcode_records(rec1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["passcode"], "1234")
        self.assertEqual(records[0]["name"], "Test")
        self.assertEqual(records[0]["passcode_id"], "01020304")

    def test_device_model_classification(self):
        """Test model classification for lock vs keypad."""
        self.assertIn(ProductModel.SESAME_5.value, LOCK_MODELS)
        self.assertNotIn(ProductModel.SESAME_TOUCH_2.value, LOCK_MODELS)
        self.assertIn(ProductModel.SESAME_TOUCH_2.value, TOUCH_MODELS)

        device_touch = Sesame5Device(
            address="AA:BB:CC:DD:EE:FF",
            secret_key=b"\x00" * 16,
            hass=MagicMock(),
            model_id=ProductModel.SESAME_TOUCH_2.value,
        )
        self.assertTrue(device_touch.is_keypad)

        device_lock = Sesame5Device(
            address="AA:BB:CC:DD:EE:11",
            secret_key=b"\x00" * 16,
            hass=MagicMock(),
            model_id=ProductModel.SESAME_5.value,
        )
        self.assertFalse(device_lock.is_keypad)


class TestCoordinatorPasscodes(unittest.IsolatedAsyncioTestCase):
    """Test coordinator passcode operations, timers, and one-time unlock triggers."""

    async def asyncSetUp(self):
        self.hass = MagicMock()
        self.hass.async_create_task = asyncio.create_task
        self.entry = MagicMock()
        self.entry.data = {"read_only": False}
        self.entry.options = {}

        self.device = MagicMock(spec=Sesame5Device)
        self.device.address = "AA:BB:CC:DD:EE:FF"
        self.device.is_ready = True
        self.device.is_keypad = True
        self.device.mech_status = None
        self.device.mech_settings = None
        self.device.history = None

        self.device.add_passcode = AsyncMock()
        self.device.delete_passcode = AsyncMock()
        self.device.request_passcodes = AsyncMock(return_value=[{"passcode": "1234", "name": "Guest"}])
        self.device.authenticate = AsyncMock()

        self.coordinator = Sesame5Coordinator(self.hass, self.entry, self.device)

    async def test_add_and_delete_passcode(self):
        """Test adding and deleting passcode via coordinator."""
        await self.coordinator.async_add_passcode("1234", name="Guest")
        self.device.add_passcode.assert_awaited_once_with("1234", "Guest")

        await self.coordinator.async_delete_passcode("1234")
        self.device.delete_passcode.assert_awaited_once_with("1234")

    async def test_one_time_passcode_trigger(self):
        """Test one-time passcode auto-deletion upon password unlock broadcast."""
        task_created = []

        def _mock_create_task(coro):
            t = asyncio.create_task(coro)
            task_created.append(t)
            return t

        self.hass.async_create_task = _mock_create_task

        await self.coordinator.async_add_passcode("5678", name="OneTimeGuest", one_time=True)
        self.assertIn("5678", self.coordinator._temp_passcodes)
        self.assertTrue(self.coordinator._temp_passcodes["5678"]["one_time"])

        # Create dummy history record simulating a password unlock event
        raw_hist = bytearray(34)
        raw_hist[0] = 0  # success
        raw_hist[1:5] = struct.pack("<I", 1)  # record_id
        raw_hist[5] = HistoryType.BLE_UNLOCK.value  # type
        raw_hist[6:10] = struct.pack("<I", int(datetime.now(timezone.utc).timestamp()))
        # tag_data: len=0, type=PASSWORD
        raw_hist[10] = 0
        raw_hist[11] = HistoryTagType.PASSWORD.value
        record = Sesame5HistoryRecord(bytes(raw_hist))

        self.coordinator.handle_one_time_unlock(record.tag_name)
        if task_created:
            await asyncio.gather(*task_created)
        self.assertTrue(len(task_created) > 0)

    async def test_connection_modes(self):
        """Test default realtime mode vs power saving mode."""
        # Default is realtime
        self.assertTrue(self.coordinator.is_realtime_mode)
        self.assertEqual(self.coordinator.connection_mode, "realtime")

        # Switch to power saving
        self.entry.options = {"connection_mode": "power_saving", "refresh_interval": 15}
        self.assertFalse(self.coordinator.is_realtime_mode)
        self.assertEqual(self.coordinator.connection_mode, "power_saving")

        self.coordinator.apply_options_update()
        self.assertIsNotNone(self.coordinator.update_interval)

        # Switch back to realtime
        self.entry.options = {"connection_mode": "realtime"}
        self.coordinator.apply_options_update()
        self.assertIsNone(self.coordinator.update_interval)
        self.assertTrue(self.coordinator.is_realtime_mode)


if __name__ == "__main__":
    unittest.main()
