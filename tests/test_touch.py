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
        """Test parsing of Touch 7/9-byte mech status (<HhhB)."""
        # raw_battery=3175 (6.35V), target=0, position=795, flags=0
        payload = struct.pack("<HhhB", 3175, 0, 795, 0) + b"\x00\x00"
        status = Sesame5MechStatus(payload)

        self.assertEqual(status.battery_voltage, 6.35)
        self.assertEqual(status.position, 795)
        self.assertEqual(status.target_position, 0)
        self.assertEqual(status.battery_percentage, 100)

    def test_lock_mech_status_parsing(self):
        """Test parsing of 7-byte Lock mech status (<HhhB)."""
        # raw_battery=2900, target=0, position=0, flags=IS_IN_LOCK_RANGE
        payload = struct.pack("<HhhB", 2900, 0, 0, MechStatusBitFlag.IS_IN_LOCK_RANGE)
        status = Sesame5MechStatus(payload)

        self.assertEqual(status.battery_voltage, 5.8)
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
        with self.assertRaises(ValueError) as ctx:
            format_passcode_add_payload("123")  # too short (< 4)
        self.assertNotIn("123", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            format_passcode_add_payload("12345678901234567")  # too long (> 16)
        self.assertNotIn("12345678901234567", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            format_passcode_add_payload("abcd")  # non-digit
        self.assertNotIn("abcd", str(ctx.exception))

    def test_format_passcode_delete_payload(self):
        """Test formatting of SSM_OS3_PASSCODE_DELETE payload."""
        # By PIN string
        payload = format_passcode_delete_payload("1234")
        self.assertEqual(payload, bytes([1, 2, 3, 4]))

        # By hex string
        payload_hex = format_passcode_delete_payload("01020304")
        self.assertEqual(payload_hex, bytes([1, 2, 3, 4]))

        # Invalid format should raise ValueError without leaking the passcode in exception message
        with self.assertRaises(ValueError) as ctx:
            format_passcode_delete_payload("invalid_code_xyz")
        self.assertNotIn("invalid_code_xyz", str(ctx.exception))

    def test_parse_passcode_records(self):
        """Test parsing of SSM_OS3_PASSCODE_NOTIFY record stream (without clear PIN digits)."""
        # Record 1: type=0, idLen=4, id=[1,2,3,4], nameLen=4, name="Test"
        rec1 = bytes([0, 4, 1, 2, 3, 4, 4]) + b"Test"
        records = parse_passcode_records(rec1)

        self.assertEqual(len(records), 1)
        self.assertNotIn("passcode", records[0])
        self.assertNotIn("id", records[0])
        self.assertEqual(records[0]["name"], "Test")
        self.assertEqual(records[0]["passcode_id"], "01020304")
        self.assertEqual(records[0]["id_hex"], "01020304")

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

    def test_entity_translation_keys(self):
        """Test sensors and binary sensors have translation_key set for localization."""
        from custom_components.sesame5_ble.sensor import (
            Sesame5BatterySensor,
            Sesame5VoltageSensor,
            Sesame5PositionSensor,
            Sesame5LastOperationSensor,
            Sesame5LastOperationTimeSensor,
            Sesame5LastUnlockOperationSensor,
            Sesame5LastUnlockTimeSensor,
            Sesame5LastLockOperationSensor,
            Sesame5LastLockTimeSensor,
            SesameTouchPasswordCountSensor,
            SesameTouchFingerprintCountSensor,
            SesameTouchCardCountSensor,
        )
        from custom_components.sesame5_ble.binary_sensor import (
            Sesame5DoorBinarySensor,
            Sesame5BatteryCriticalBinarySensor,
            Sesame5MovingBinarySensor,
        )

        coord = MagicMock()
        coord.address = "AA:BB:CC:DD:EE:FF"
        entry = MagicMock()
        entry.data = {}

        # Sensors
        self.assertEqual(Sesame5BatterySensor(coord, entry).translation_key, "battery")
        self.assertEqual(Sesame5VoltageSensor(coord, entry).translation_key, "voltage")
        self.assertEqual(Sesame5PositionSensor(coord, entry).translation_key, "angle")

        # Operation sensors (backwards-compatible unique IDs & translation keys)
        last_op = Sesame5LastOperationSensor(coord, entry)
        self.assertEqual(last_op.translation_key, "last_operation")
        self.assertEqual(last_op.unique_id, "AA:BB:CC:DD:EE:FF_last_operation")

        last_op_time = Sesame5LastOperationTimeSensor(coord, entry)
        self.assertEqual(last_op_time.translation_key, "last_operation_time")
        self.assertEqual(last_op_time.unique_id, "AA:BB:CC:DD:EE:FF_last_operation_time")
        self.assertIsNone(getattr(last_op_time, "entity_category", None))

        last_unlock = Sesame5LastUnlockOperationSensor(coord, entry)
        self.assertEqual(last_unlock.translation_key, "last_unlock_operation")
        self.assertEqual(last_unlock.unique_id, "AA:BB:CC:DD:EE:FF_last_unlock_operation")

        last_unlock_time = Sesame5LastUnlockTimeSensor(coord, entry)
        self.assertEqual(last_unlock_time.translation_key, "last_unlock_time")
        self.assertEqual(last_unlock_time.unique_id, "AA:BB:CC:DD:EE:FF_last_unlock_time")
        self.assertIsNone(getattr(last_unlock_time, "entity_category", None))

        last_lock = Sesame5LastLockOperationSensor(coord, entry)
        self.assertEqual(last_lock.translation_key, "last_lock_operation")
        self.assertEqual(last_lock.unique_id, "AA:BB:CC:DD:EE:FF_last_lock_operation")

        last_lock_time = Sesame5LastLockTimeSensor(coord, entry)
        self.assertEqual(last_lock_time.translation_key, "last_lock_time")
        self.assertEqual(last_lock_time.unique_id, "AA:BB:CC:DD:EE:FF_last_lock_time")
        self.assertIsNone(getattr(last_lock_time, "entity_category", None))

        self.assertEqual(SesameTouchPasswordCountSensor(coord, entry).translation_key, "password_count")
        self.assertEqual(SesameTouchFingerprintCountSensor(coord, entry).translation_key, "fingerprint_count")
        self.assertEqual(SesameTouchCardCountSensor(coord, entry).translation_key, "card_count")

        # Binary sensors
        self.assertEqual(Sesame5DoorBinarySensor(coord, entry).translation_key, "door")
        self.assertEqual(Sesame5BatteryCriticalBinarySensor(coord, entry).translation_key, "battery_critical")
        self.assertEqual(Sesame5MovingBinarySensor(coord, entry).translation_key, "moving")

    def test_selector_translation_parity(self):
        """Test selector translations exist and match in strings.json, en.json, zh-Hans.json, ja.json."""
        import json
        from pathlib import Path

        base_dir = Path(__file__).parent.parent / "custom_components" / "sesame5_ble"
        files = {
            "strings": base_dir / "strings.json",
            "en": base_dir / "translations" / "en.json",
            "zh-Hans": base_dir / "translations" / "zh-Hans.json",
            "ja": base_dir / "translations" / "ja.json",
        }

        data = {}
        for name, path in files.items():
            self.assertTrue(path.exists(), f"Missing {path}")
            with open(path, "r", encoding="utf-8") as f:
                data[name] = json.load(f)

        # Check selector keys
        for name, doc in data.items():
            self.assertIn("selector", doc, f"Missing selector section in {name}")
            self.assertIn("connection_mode", doc["selector"], f"Missing connection_mode in {name}")
            self.assertIn("realtime", doc["selector"]["connection_mode"]["options"], f"Missing realtime in {name}")
            self.assertIn("power_saving", doc["selector"]["connection_mode"]["options"], f"Missing power_saving in {name}")
            self.assertIn("linked_lock", doc["selector"], f"Missing linked_lock in {name}")
            self.assertIn("auto", doc["selector"]["linked_lock"]["options"], f"Missing auto in {name}")
            self.assertIn("device_selection", doc["selector"], f"Missing device_selection in {name}")
            self.assertIn("manual", doc["selector"]["device_selection"]["options"], f"Missing manual in {name}")

            # Check no_devices step and bluetooth_not_available abort
            self.assertIn("no_devices", doc["config"]["step"], f"Missing no_devices step in {name}")
            self.assertIn("manual", doc["config"]["step"]["no_devices"]["menu_options"], f"Missing manual in no_devices in {name}")
            self.assertIn("retry", doc["config"]["step"]["no_devices"]["menu_options"], f"Missing retry in no_devices in {name}")
            self.assertIn("bluetooth_not_available", doc["config"]["abort"], f"Missing bluetooth_not_available abort in {name}")

    async def test_operation_sensors_state_restoration(self):
        """Test sensors restore last state on HA restart when live data is not yet available."""
        from custom_components.sesame5_ble.sensor import (
            Sesame5LastOperationSensor,
            Sesame5LastUnlockOperationSensor,
            Sesame5LastLockOperationSensor,
        )

        coord = MagicMock()
        coord.data = None
        coord.address = "AA:BB:CC:DD:EE:FF"
        entry = MagicMock()
        entry.data = {}

        sensor = Sesame5LastUnlockOperationSensor(coord, entry)
        mock_last_state = MagicMock()
        mock_last_state.state = "门外指纹解锁"
        mock_last_state.attributes = {"source": "outside"}
        sensor.async_get_last_state = AsyncMock(return_value=mock_last_state)

        await sensor.async_added_to_hass()
        self.assertEqual(sensor.native_value, "门外指纹解锁")
        self.assertEqual(sensor.extra_state_attributes.get("source"), "outside")


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
        """Test keypad vs lock connection modes."""
        # Keypad must always report False for is_realtime_mode to save battery
        self.assertFalse(self.coordinator.is_realtime_mode)
        self.assertEqual(self.coordinator.connection_mode, "power_saving")

        # Now test a lock device
        lock_device = MagicMock(spec=Sesame5Device)
        lock_device.address = "AA:BB:CC:DD:EE:11"
        lock_device.is_ready = True
        lock_device.is_keypad = False
        lock_device.mech_status = None
        lock_device.mech_settings = None
        lock_device.history = None

        lock_entry = MagicMock()
        lock_entry.data = {"read_only": False}
        lock_entry.options = {}

        lock_coordinator = Sesame5Coordinator(self.hass, lock_entry, lock_device)

        # Default for lock is realtime
        self.assertTrue(lock_coordinator.is_realtime_mode)
        self.assertEqual(lock_coordinator.connection_mode, "realtime")

        # Switch lock to power saving
        lock_entry.options = {"connection_mode": "power_saving", "refresh_interval": 15}
        self.assertFalse(lock_coordinator.is_realtime_mode)
        self.assertEqual(lock_coordinator.connection_mode, "power_saving")

        lock_coordinator.apply_options_update()
        self.assertIsNotNone(lock_coordinator.update_interval)

        # Switch lock back to realtime
        lock_entry.options = {"connection_mode": "realtime"}
        lock_coordinator.apply_options_update()
        self.assertIsNone(lock_coordinator.update_interval)
        self.assertTrue(lock_coordinator.is_realtime_mode)

    async def test_linked_lock_filtering(self):
        """Test keypad linked lock binding and filtering of history broadcasts."""
        await self.coordinator.async_add_passcode("9999", name="LinkedGuest", one_time=True)
        self.assertIn("9999", self.coordinator._temp_passcodes)

        # Create dummy history record simulating a password unlock event
        raw_hist = bytearray(35)
        raw_hist[0] = 0
        raw_hist[1:5] = struct.pack("<I", 1)
        raw_hist[5] = HistoryType.BLE_UNLOCK.value
        raw_hist[6:10] = struct.pack("<I", int(datetime.now(timezone.utc).timestamp()))
        # tag_data starts at index 17 (1B len, 1B tag_type, 16B accessory_uuid)
        raw_hist[17] = 0
        raw_hist[18] = HistoryTagType.PASSWORD.value
        raw_hist[19:35] = b"\x01" * 16
        record = Sesame5HistoryRecord(bytes(raw_hist))

        # 1. Keypad bound specifically to Lock 1 (11:11:11:11:11:11)
        self.entry.options = {"linked_lock": "11:11:11:11:11:11"}
        self.assertEqual(self.coordinator.linked_lock, "11:11:11:11:11:11")

        with patch.object(self.coordinator, "handle_one_time_unlock") as mock_handle:
            # Broadcast from different lock 22:22:22:22:22:22 -> should be ignored
            self.coordinator._on_history_broadcast({"address": "22:22:22:22:22:22", "history": record})
            mock_handle.assert_not_called()

            # Broadcast from bound lock 11:11:11:11:11:11 -> should trigger
            self.coordinator._on_history_broadcast({"address": "11:11:11:11:11:11", "history": record})
            mock_handle.assert_called_once()

        # 2. Keypad bound to 'auto' -> accepts unlock from any lock
        self.entry.options = {"linked_lock": "auto"}
        self.assertEqual(self.coordinator.linked_lock, "auto")

        with patch.object(self.coordinator, "handle_one_time_unlock") as mock_handle:
            self.coordinator._on_history_broadcast({"address": "33:33:33:33:33:33", "history": record})
            mock_handle.assert_called_once()

        # 3. Lock coordinator should ignore history broadcasts (only keypads process them)
        lock_device = MagicMock(spec=Sesame5Device)
        lock_device.address = "11:11:11:11:11:11"
        lock_device.is_keypad = False
        lock_coordinator = Sesame5Coordinator(self.hass, self.entry, lock_device)
        with patch.object(lock_coordinator, "handle_one_time_unlock") as mock_handle:
            lock_coordinator._on_history_broadcast({"address": "11:11:11:11:11:11", "history": record})
            mock_handle.assert_not_called()

    def test_get_configured_locks(self):
        """Test _get_configured_locks returns only locks and excludes keypads and self."""
        from custom_components.sesame5_ble.config_flow import _get_configured_locks

        mock_entry_lock = MagicMock()
        mock_entry_lock.data = {
            "address": "11:22:33:44:55:66",
            "model_id": ProductModel.SESAME_5.value,
            "model": "Sesame 5",
        }
        mock_entry_lock.title = "Front Door"

        mock_entry_touch = MagicMock()
        mock_entry_touch.data = {
            "address": "AA:BB:CC:DD:EE:FF",
            "model_id": ProductModel.SESAME_TOUCH_2.value,
            "model": "Sesame Touch 2",
        }
        mock_entry_touch.title = "Keypad"

        self.hass.config_entries.async_entries.return_value = [mock_entry_lock, mock_entry_touch]

        locks = _get_configured_locks(self.hass, exclude_address="AA:BB:CC:DD:EE:FF")
        self.assertEqual(len(locks), 2)  # auto + Front Door
        self.assertEqual(locks[0]["value"], "auto")
        self.assertEqual(locks[1]["value"], "11:22:33:44:55:66")
        self.assertIn("Front Door", locks[1]["label"])

    async def test_options_flow_lock_vs_keypad(self):
        """Test options flow shows step 'keypad' for Touch devices and step 'init' for Locks."""
        from custom_components.sesame5_ble.config_flow import Sesame5OptionsFlowHandler

        # 1. Keypad options flow
        keypad_handler = Sesame5OptionsFlowHandler()
        keypad_handler.hass = self.hass
        keypad_entry = MagicMock()
        keypad_entry.data = {
            "address": "AA:BB:CC:DD:EE:FF",
            "model_id": ProductModel.SESAME_TOUCH_2.value,
            "model": "Sesame Touch 2",
        }
        keypad_entry.options = {}
        keypad_entry.title = "Sesame Touch 2"
        keypad_entry.runtime_data = None
        keypad_handler.config_entry = keypad_entry

        result_keypad = await keypad_handler.async_step_init()
        self.assertEqual(result_keypad["type"], "form")
        self.assertEqual(result_keypad["step_id"], "keypad")

        # 2. Lock options flow
        lock_handler = Sesame5OptionsFlowHandler()
        lock_handler.hass = self.hass
        lock_entry = MagicMock()
        lock_entry.data = {
            "address": "11:22:33:44:55:66",
            "model_id": ProductModel.SESAME_5.value,
            "model": "Sesame 5",
        }
        lock_entry.options = {}
        lock_entry.title = "Sesame 5"
        lock_entry.runtime_data = None
        lock_handler.config_entry = lock_entry

        result_lock = await lock_handler.async_step_init()
        self.assertEqual(result_lock["type"], "form")
        self.assertEqual(result_lock["step_id"], "init")


    async def test_credential_counts_and_events(self):
        """Test keypad credential reception and counts."""
        device = Sesame5Device(
            address="AA:BB:CC:DD:EE:FF",
            secret_key=b"\x00" * 16,
            hass=MagicMock(),
            model_id=ProductModel.SESAME_TOUCH_2_PRO.value,
        )
        self.assertEqual(device.fingerprint_count, 0)
        self.assertEqual(device.passcode_count, 0)
        self.assertEqual(device.card_count, 0)

        # 1. Fingerprint notify stream
        await device._handle_publish(ItemCode.FINGERPRINT_FIRST.value, b"")
        fp_payload = bytes([1, 2, 0x11, 0x22, 5]) + b"Thumb"
        await device._handle_publish(ItemCode.FINGERPRINT_NOTIFY.value, fp_payload)
        await device._handle_publish(ItemCode.FINGERPRINT_LAST.value, b"")

        self.assertEqual(device.fingerprint_count, 1)
        self.assertEqual(len(device.fingerprints), 1)
        self.assertEqual(device.fingerprints[0]["name"], "Thumb")
        self.assertEqual(device.fingerprints[0]["id_hex"], "1122")

        # 2. Card notify stream
        await device._handle_publish(ItemCode.CARD_FIRST.value, b"")
        card_payload = bytes([0, 4, 0xAA, 0xBB, 0xCC, 0xDD, 4]) + b"Card"
        await device._handle_publish(ItemCode.CARD_NOTIFY.value, card_payload)
        await device._handle_publish(ItemCode.CARD_LAST.value, b"")

        self.assertEqual(device.card_count, 1)
        self.assertEqual(len(device.cards), 1)
        self.assertEqual(device.cards[0]["name"], "Card")

        # 3. Passcode notify stream
        await device._handle_publish(ItemCode.SSM_OS3_PASSCODE_FIRST.value, b"")
        pwd_payload = bytes([0, 4, 1, 2, 3, 4, 4]) + b"Home"
        await device._handle_publish(ItemCode.SSM_OS3_PASSCODE_NOTIFY.value, pwd_payload)
        await device._handle_publish(ItemCode.SSM_OS3_PASSCODE_LAST.value, b"")

        self.assertEqual(device.passcode_count, 1)
        self.assertEqual(len(device.passcodes), 1)
        self.assertNotIn("passcode", device.passcodes[0])
        self.assertEqual(device.passcodes[0]["passcode_id"], "01020304")
        self.assertEqual(device.passcodes[0]["name"], "Home")

    async def test_config_flow_candidate_filtering_and_abort(self):
        """Test config flow filters already configured devices and aborts on duplicates."""
        from custom_components.sesame5_ble.config_flow import Sesame5ConfigFlow
        from custom_components.sesame5_ble.const import CONF_ADDRESS

        flow = Sesame5ConfigFlow()
        flow.hass = self.hass

        entry_a = MagicMock()
        entry_a.unique_id = "AA:BB:CC:DD:EE:01"
        entry_a.data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:01"}
        self.hass.config_entries.async_entries.return_value = [entry_a]

        # 1. Scanned devices contain both device A (configured) and device B (unconfigured)
        scanned_devices = [
            {"address": "AA:BB:CC:DD:EE:01", "name": "Sesame 5 (AA:BB:CC:DD:EE:01)", "rssi": -60, "model": "Sesame 5", "model_id": 0, "device_id": "1"},
            {"address": "AA:BB:CC:DD:EE:02", "name": "Sesame 5 (AA:BB:CC:DD:EE:02)", "rssi": -70, "model": "Sesame 5", "model_id": 0, "device_id": "2"},
        ]

        with patch("custom_components.sesame5_ble.config_flow._scan_sesame5_devices", return_value=scanned_devices):
            with patch.object(flow, "_async_current_ids", return_value={"AA:BB:CC:DD:EE:01"}):
                result = await flow.async_step_user()
                self.assertEqual(result["type"], "form")
                self.assertEqual(result["step_id"], "user")

                # Discovered devices dictionary should ONLY contain device B (AA:BB:CC:DD:EE:02)
                self.assertNotIn("AA:BB:CC:DD:EE:01", flow._discovered_devices)
                self.assertIn("AA:BB:CC:DD:EE:02", flow._discovered_devices)

        # 2. When ALL scanned devices are already configured (or none found), show no_devices menu
        scanned_only_a = [
            {"address": "AA:BB:CC:DD:EE:01", "name": "Sesame 5 (AA:BB:CC:DD:EE:01)", "rssi": -60, "model": "Sesame 5", "model_id": 0, "device_id": "1"},
        ]
        flow2 = Sesame5ConfigFlow()
        flow2.hass = self.hass
        with patch("custom_components.sesame5_ble.config_flow._scan_sesame5_devices", return_value=scanned_only_a):
            with patch.object(flow2, "_async_current_ids", return_value={"AA:BB:CC:DD:EE:01"}):
                result2 = await flow2.async_step_user()
                self.assertEqual(result2["type"], "menu")
                self.assertEqual(result2["step_id"], "no_devices")
                self.assertEqual(result2["menu_options"], ["manual", "retry"])

        # 3. If user manually enters an already configured MAC, abort immediately
        flow3 = Sesame5ConfigFlow()
        flow3.hass = self.hass
        flow3._abort_if_unique_id_configured = MagicMock(side_effect=Exception("ABORT_CONFIGURED"))
        with self.assertRaises(Exception) as ctx:
            await flow3.async_step_manual({CONF_ADDRESS: "AA:BB:CC:DD:EE:01"})
        self.assertIn("ABORT_CONFIGURED", str(ctx.exception))

        # 4. If HA has NO Bluetooth adapters, immediately abort with bluetooth_not_available
        flow4 = Sesame5ConfigFlow()
        flow4.hass = self.hass
        with patch("custom_components.sesame5_ble.config_flow.async_scanner_count", return_value=0):
            result4 = await flow4.async_step_user()
            self.assertEqual(result4["type"], "abort")
            self.assertEqual(result4["reason"], "bluetooth_not_available")

            result4_manual = await flow4.async_step_manual()
            self.assertEqual(result4_manual["type"], "abort")
            self.assertEqual(result4_manual["reason"], "bluetooth_not_available")

        # 5. Test retry step triggers active BLE scan and returns to user step
        flow5 = Sesame5ConfigFlow()
        flow5.hass = self.hass
        with patch("custom_components.sesame5_ble.config_flow.async_request_active_scan", new_callable=AsyncMock) as mock_scan:
            with patch.object(flow5, "async_step_user", new_callable=AsyncMock) as mock_user:
                await flow5.async_step_retry()
                mock_scan.assert_called_once_with(self.hass)
                mock_user.assert_called_once()

        # 6. Test manual step model dropdown selection and model_id mapping
        flow6 = Sesame5ConfigFlow()
        flow6.hass = self.hass
        with patch.object(flow6, "async_step_auth", new_callable=AsyncMock) as mock_auth:
            await flow6.async_step_manual({CONF_ADDRESS: "AA:BB:CC:DD:EE:99", "model": "Sesame Touch 2 Pro"})
            self.assertEqual(flow6._selected_model, "Sesame Touch 2 Pro")
            self.assertEqual(flow6._selected_model_id, ProductModel.SESAME_TOUCH_2_PRO.value)
            mock_auth.assert_called_once()

    async def test_admin_services_and_sanitized_get_passcodes(self):
        """Test passcode services are admin-only and get_passcodes returns only type and name."""
        import custom_components.sesame5_ble as init_mod
        from custom_components.sesame5_ble.const import (
            CONF_MODEL_ID,
            CONF_SECRET_KEY,
            SERVICE_ADD_PASSCODE,
            SERVICE_DELETE_PASSCODE,
            SERVICE_GET_PASSCODES,
        )

        # 1. Verify coordinator.async_get_passcodes returns ONLY type and name (no hex IDs or PINs)
        self.device.request_passcodes = AsyncMock(
            return_value=[
                {
                    "type": 0,
                    "id_hex": "01020304",
                    "name": "Guest",
                    "passcode_id": "01020304",
                }
            ]
        )
        sanitized = await self.coordinator.async_get_passcodes()
        self.assertEqual(sanitized, [{"type": 0, "name": "Guest"}])
        self.assertEqual(set(sanitized[0].keys()), {"type", "name"})
        # Internal cache in coordinator still retains the ID for delete lookup
        self.assertEqual(self.coordinator._passcode_cache[0]["id_hex"], "01020304")

        # 2. Verify async_setup_entry registers all 3 passcode services via async_register_admin_service
        mock_hass = MagicMock()
        mock_hass.services.has_service.return_value = False
        mock_hass.services.async_register = MagicMock()
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock()
        mock_hass.config_entries.async_entries.return_value = []

        mock_entry = MagicMock()
        mock_entry.data = {
            "address": "AA:BB:CC:DD:EE:FF",
            CONF_SECRET_KEY: "00" * 16,
            CONF_MODEL_ID: ProductModel.SESAME_TOUCH_2.value,
        }
        mock_entry.options = {}

        registered_handlers = {}

        def _capture_admin_service(hass_arg, domain, service, handler, **kwargs):
            registered_handlers[service] = (handler, kwargs)

        with patch("custom_components.sesame5_ble.Sesame5Device", return_value=self.device):
            with patch("custom_components.sesame5_ble.Sesame5Coordinator", return_value=self.coordinator):
                with patch.object(self.coordinator, "async_config_entry_first_refresh", new_callable=AsyncMock):
                    with patch(
                        "custom_components.sesame5_ble.async_register_admin_service",
                        side_effect=_capture_admin_service,
                    ) as mock_admin_reg:
                        mock_entry.runtime_data = self.coordinator
                        mock_hass.config_entries.async_entries.return_value = [mock_entry]
                        result = await init_mod.async_setup_entry(mock_hass, mock_entry)

        self.assertTrue(result)
        # Must NEVER register passcode services with plain non-admin async_register
        mock_hass.services.async_register.assert_not_called()
        self.assertEqual(mock_admin_reg.call_count, 3)
        self.assertIn(SERVICE_ADD_PASSCODE, registered_handlers)
        self.assertIn(SERVICE_DELETE_PASSCODE, registered_handlers)
        self.assertIn(SERVICE_GET_PASSCODES, registered_handlers)

        # 3. Call the registered get_passcodes handler and confirm response omits ALL IDs and PINs
        get_handler, _ = registered_handlers[SERVICE_GET_PASSCODES]
        mock_call = MagicMock()
        mock_call.data = {"address": "AA:BB:CC:DD:EE:FF"}
        response = await get_handler(mock_call)
        self.assertEqual(
            response,
            {
                "devices": {
                    "AA:BB:CC:DD:EE:FF": [{"type": 0, "name": "Guest"}]
                }
            },
        )
        entry_resp = response["devices"]["AA:BB:CC:DD:EE:FF"][0]
        self.assertEqual(set(entry_resp.keys()), {"type", "name"})

        # 4. Call delete_passcode service handler by name
        delete_handler, _ = registered_handlers[SERVICE_DELETE_PASSCODE]
        self.device.delete_passcode.reset_mock()
        del_call = MagicMock()
        del_call.data = {"address": "AA:BB:CC:DD:EE:FF", "name": "Guest"}
        await delete_handler(del_call)
        self.device.delete_passcode.assert_awaited_once_with("01020304")

        # Calling delete_passcode service without name or passcode must raise HomeAssistantError
        from homeassistant.exceptions import HomeAssistantError

        empty_call = MagicMock()
        empty_call.data = {"address": "AA:BB:CC:DD:EE:FF"}
        with self.assertRaises(HomeAssistantError):
            await delete_handler(empty_call)

    async def test_delete_passcode_by_name_and_digits(self):
        """Test deleting passcodes by name (cached & cold lookup), by PIN digits, and timer cleanup."""
        from homeassistant.exceptions import HomeAssistantError

        # 1. Cold cache lookup: deleting by name in `passcode` field triggers request_passcodes()
        self.coordinator._passcode_cache = []
        self.device.passcodes = []
        self.device.request_passcodes = AsyncMock(
            return_value=[{"type": 0, "id_hex": "01020304", "name": "Cleaner", "passcode_id": "01020304"}]
        )
        await self.coordinator.async_delete_passcode("Cleaner")
        self.device.request_passcodes.assert_awaited_once()
        self.device.delete_passcode.assert_awaited_once_with("01020304")
        # Cache should now have evicted Cleaner
        self.assertEqual(self.coordinator._passcode_cache, [])

        # 2. Deleting a temporary passcode by name cancels its timer
        self.device.delete_passcode.reset_mock()
        mock_unsub = MagicMock()
        self.coordinator._temp_passcodes["5678"] = {
            "name": "TempGuest",
            "duration": 600,
            "one_time": False,
            "unsub": mock_unsub,
        }
        self.coordinator._passcode_cache = [
            {"type": 0, "id_hex": "05060708", "name": "TempGuest", "passcode_id": "05060708"}
        ]
        await self.coordinator.async_delete_passcode(name="TempGuest")
        mock_unsub.assert_called_once()
        self.assertNotIn("5678", self.coordinator._temp_passcodes)
        self.device.delete_passcode.assert_awaited_once_with("05060708")

        # 3. Deleting by raw PIN digits stays supported directly
        self.device.delete_passcode.reset_mock()
        self.device.request_passcodes.reset_mock()
        await self.coordinator.async_delete_passcode("9988")
        self.device.request_passcodes.assert_not_awaited()
        self.device.delete_passcode.assert_awaited_once_with("9988")

        # 4. Deleting a non-existent name raises HomeAssistantError
        self.device.request_passcodes = AsyncMock(return_value=[])
        with self.assertRaises(HomeAssistantError):
            await self.coordinator.async_delete_passcode(name="NoSuchUser")

    async def test_secret_key_uses_password_text_selector(self):
        """Test both lock and keypad auth config flow steps mask secret_key using PASSWORD selector."""
        from custom_components.sesame5_ble.config_flow import Sesame5ConfigFlow
        from custom_components.sesame5_ble.const import CONF_SECRET_KEY
        from homeassistant.helpers.selector import TextSelector, TextSelectorType

        # 1. Standard lock auth step
        flow_lock = Sesame5ConfigFlow()
        flow_lock.hass = self.hass
        flow_lock._selected_address = "AA:BB:CC:DD:EE:01"
        flow_lock._selected_model = "Sesame 5"
        flow_lock._selected_model_id = ProductModel.SESAME_5.value

        res_lock = await flow_lock.async_step_auth()
        self.assertEqual(res_lock["step_id"], "auth")
        lock_schema = res_lock["data_schema"].schema
        lock_selector = lock_schema[CONF_SECRET_KEY]
        self.assertIsInstance(lock_selector, TextSelector)
        self.assertEqual(lock_selector.config.type, TextSelectorType.PASSWORD)

        # 2. Keypad auth step
        flow_kp = Sesame5ConfigFlow()
        flow_kp.hass = self.hass
        flow_kp._selected_address = "AA:BB:CC:DD:EE:02"
        flow_kp._selected_model = "Sesame Touch 2 Pro"
        flow_kp._selected_model_id = ProductModel.SESAME_TOUCH_2_PRO.value

        res_kp = await flow_kp.async_step_auth_keypad()
        self.assertEqual(res_kp["step_id"], "auth_keypad")
        kp_schema = res_kp["data_schema"].schema
        kp_selector = kp_schema[CONF_SECRET_KEY]
        self.assertIsInstance(kp_selector, TextSelector)
        self.assertEqual(kp_selector.config.type, TextSelectorType.PASSWORD)


if __name__ == "__main__":
    unittest.main()
