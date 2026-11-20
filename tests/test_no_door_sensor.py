"""Tests verifying normal and logical integration behavior when NO door sensor is paired."""

import asyncio
from datetime import datetime, timezone
import struct
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import tests  # Preload HA stubs
from custom_components.sesame5_ble.binary_sensor import (
    Sesame5BatteryCriticalBinarySensor,
    Sesame5DoorBinarySensor,
    Sesame5MovingBinarySensor,
)
from custom_components.sesame5_ble.const import (
    CONF_MODEL_ID,
    HistoryTagType,
    HistoryType,
    ItemCode,
    ResultCode,
)
from custom_components.sesame5_ble.coordinator import Sesame5Coordinator, Sesame5State
from custom_components.sesame5_ble.device import STATE_READY, Sesame5Device
from custom_components.sesame5_ble.helpers import Sesame5HistoryRecord, Sesame5MechStatus
from custom_components.sesame5_ble.lock import Sesame5BleLock
from custom_components.sesame5_ble.sensor import (
    Sesame5BatterySensor,
    Sesame5LastLockOperationSensor,
    Sesame5LastLockTimeSensor,
    Sesame5LastOperationSensor,
    Sesame5LastOperationTimeSensor,
    Sesame5LastUnlockOperationSensor,
    Sesame5LastUnlockTimeSensor,
    Sesame5PositionSensor,
    Sesame5VoltageSensor,
)


class TestNoDoorSensorBehavior(unittest.IsolatedAsyncioTestCase):
    """Verify integration behavior when Sesame 5 lock is used without an Open Sensor."""

    async def asyncSetUp(self):
        self.mock_hass = MagicMock()
        self.address = "AA:BB:CC:DD:EE:01"
        self.secret_key = bytes(range(16))
        self.device = Sesame5Device(self.address, self.secret_key, self.mock_hass, model_id=0)
        self.device._client = MagicMock(is_connected=True)
        self.device._state = STATE_READY

        # Mock config entry
        self.mock_entry = MagicMock()
        self.mock_entry.data = {
            "address": self.address,
            CONF_MODEL_ID: 0,  # Sesame 5
        }

        # Coordinator
        self.coordinator = Sesame5Coordinator(self.mock_hass, self.mock_entry, self.device)

    def test_initial_state_without_door_sensor(self):
        """Test initial setup has door_open = None, door binary sensor is_on = None (unknown in HA)."""
        mech = Sesame5MechStatus(struct.pack("<HhhB", 3000, 0, 90, 0x12))
        self.device._mech_status = mech
        self.coordinator.data = self.coordinator._current_state

        door_sensor = Sesame5DoorBinarySensor(self.coordinator, self.mock_entry)
        moving_sensor = Sesame5MovingBinarySensor(self.coordinator, self.mock_entry)
        batt_crit_sensor = Sesame5BatteryCriticalBinarySensor(self.coordinator, self.mock_entry)

        # door_open is None, meaning in HA it renders as "unknown" (未知)
        self.assertIsNone(door_sensor.is_on)
        self.assertFalse(moving_sensor.is_on)
        self.assertFalse(batt_crit_sensor.is_on)

        # When no door sensor is detected, it must default to hidden in entity registry
        self.assertFalse(door_sensor._attr_entity_registry_visible_default)

        # When a door sensor IS detected, it must be visible by default
        self.device.set_door_open(True)
        self.coordinator.data = self.coordinator._current_state
        door_sensor_with_open = Sesame5DoorBinarySensor(self.coordinator, self.mock_entry)
        self.assertTrue(door_sensor_with_open._attr_entity_registry_visible_default)
        self.device.set_door_open(None)
        self.coordinator.data = self.coordinator._current_state

        # Standard sensors behave normally
        lock = Sesame5BleLock(self.coordinator, self.mock_entry)
        self.assertTrue(lock.is_locked)
        self.assertIsNone(lock.extra_state_attributes.get("last_operation_method"))
        self.assertIsNone(lock.extra_state_attributes.get("last_unlock_method"))
        self.assertIsNone(lock.extra_state_attributes.get("last_lock_method"))

    def test_manual_unlock_and_lock_without_door_sensor(self):
        """Test manual thumbturn unlock and lock updates operations while door_open stays None."""
        door_sensor = Sesame5DoorBinarySensor(self.coordinator, self.mock_entry)
        last_op_sensor = Sesame5LastOperationSensor(self.coordinator, self.mock_entry)
        last_unlock_sensor = Sesame5LastUnlockOperationSensor(self.coordinator, self.mock_entry)
        last_lock_sensor = Sesame5LastLockOperationSensor(self.coordinator, self.mock_entry)
        last_op_time = Sesame5LastOperationTimeSensor(self.coordinator, self.mock_entry)
        last_unlock_time = Sesame5LastUnlockTimeSensor(self.coordinator, self.mock_entry)
        last_lock_time = Sesame5LastLockTimeSensor(self.coordinator, self.mock_entry)
        lock = Sesame5BleLock(self.coordinator, self.mock_entry)

        # 1. Manual Inside Unlock (HistoryType.MANUAL_UNLOCKED = 8)
        ts_unlock = 1732000000
        # raw: result(1B)=0, record_id(4B)=101, type(1B)=8, timestamp(4B), mech(7B)=b"", tag_len(1B)=0
        unlock_payload = struct.pack("<BiBI7sB", 0, 101, HistoryType.MANUAL_UNLOCKED.value, ts_unlock, b"\x00" * 7, 0)
        unlock_record = Sesame5HistoryRecord(unlock_payload)
        self.device._process_history_record(unlock_record)
        self.device._mech_status = Sesame5MechStatus(struct.pack("<HhhB", 3000, 0, 200, 0x14))  # Unlocked
        self.coordinator.data = self.coordinator._current_state

        # Verify operations
        self.assertEqual(last_op_sensor.native_value, "门内手动解锁")
        self.assertEqual(last_unlock_sensor.native_value, "门内手动解锁")
        self.assertIsNone(last_lock_sensor.native_value)
        self.assertEqual(last_op_time.native_value, datetime.fromtimestamp(ts_unlock, tz=timezone.utc))
        self.assertEqual(last_unlock_time.native_value, datetime.fromtimestamp(ts_unlock, tz=timezone.utc))
        self.assertIsNone(last_lock_time.native_value)

        # Door sensor remains None (no open sensor)
        self.assertIsNone(door_sensor.is_on)
        self.assertIsNone(self.device.door_open)

        # Lock entity attributes
        attrs = lock.extra_state_attributes
        self.assertEqual(attrs["last_operation_method"], "门内手动解锁")
        self.assertEqual(attrs["last_unlock_method"], "门内手动解锁")
        self.assertIsNone(attrs.get("last_lock_method"))

        # 2. Manual Inside Lock (HistoryType.MANUAL_LOCKED = 7)
        ts_lock = 1732000060
        lock_payload = struct.pack("<BiBI7sB", 0, 102, HistoryType.MANUAL_LOCKED.value, ts_lock, b"\x00" * 7, 0)
        lock_record = Sesame5HistoryRecord(lock_payload)
        self.device._process_history_record(lock_record)
        self.device._mech_status = Sesame5MechStatus(struct.pack("<HhhB", 3000, 0, 90, 0x12))  # Locked
        self.coordinator.data = self.coordinator._current_state

        self.assertEqual(last_op_sensor.native_value, "门内手动上锁")
        self.assertEqual(last_lock_sensor.native_value, "门内手动上锁")
        # Unlock operation is preserved!
        self.assertEqual(last_unlock_sensor.native_value, "门内手动解锁")
        self.assertEqual(last_lock_time.native_value, datetime.fromtimestamp(ts_lock, tz=timezone.utc))
        self.assertEqual(last_unlock_time.native_value, datetime.fromtimestamp(ts_unlock, tz=timezone.utc))

        # Door sensor still None
        self.assertIsNone(door_sensor.is_on)
        self.assertIsNone(self.device.door_open)

    def test_timed_autolock_without_door_sensor(self):
        """Test timer-based auto-lock (HistoryType.AUTOLOCK = 6) operates correctly without door sensor.

        Sesame locks support timed auto-lock (e.g. lock after 10s) even when NO door sensor is installed.
        It must report '自动上锁' and NOT '关门自动上锁'.
        """
        last_op_sensor = Sesame5LastOperationSensor(self.coordinator, self.mock_entry)
        last_unlock_sensor = Sesame5LastUnlockOperationSensor(self.coordinator, self.mock_entry)
        last_lock_sensor = Sesame5LastLockOperationSensor(self.coordinator, self.mock_entry)
        door_sensor = Sesame5DoorBinarySensor(self.coordinator, self.mock_entry)

        # 1. Unlock via BLE/App first (HistoryType.BLE_UNLOCK = 2)
        ts_unlock = 1732000100
        ble_unlock_payload = struct.pack("<BiBI7sB", 0, 103, HistoryType.BLE_UNLOCK.value, ts_unlock, b"\x00" * 7, 0)
        self.device._process_history_record(Sesame5HistoryRecord(ble_unlock_payload))

        # 2. Lock automatically triggers after countdown timer (HistoryType.AUTOLOCK = 6)
        ts_autolock = 1732000115
        autolock_payload = struct.pack("<BiBI7sB", 0, 104, HistoryType.AUTOLOCK.value, ts_autolock, b"\x00" * 7, 0)
        autolock_record = Sesame5HistoryRecord(autolock_payload)

        # Verify record semantics
        self.assertTrue(autolock_record.is_lock_operation)
        self.assertEqual(autolock_record.action, "lock")
        self.assertEqual(autolock_record.source, "auto")
        self.assertEqual(autolock_record.description_zh, "自动上锁")
        self.assertIsNone(autolock_record.door_open)

        self.device._process_history_record(autolock_record)
        self.device._mech_status = Sesame5MechStatus(struct.pack("<HhhB", 3000, 0, 90, 0x12))
        self.coordinator.data = self.coordinator._current_state

        # Operations must distinguish timed autolock from open-sensor autolock
        self.assertEqual(last_op_sensor.native_value, "自动上锁")
        self.assertEqual(last_lock_sensor.native_value, "自动上锁")
        self.assertEqual(last_unlock_sensor.native_value, "蓝牙/App 解锁")

        # door_open remains None
        self.assertIsNone(door_sensor.is_on)
        self.assertIsNone(self.device.door_open)

    def test_keypad_unlock_and_ble_commands_without_door_sensor(self):
        """Test Keypad fingerprint unlock and BLE lock/unlock commands without door sensor."""
        last_op_sensor = Sesame5LastOperationSensor(self.coordinator, self.mock_entry)
        last_unlock_sensor = Sesame5LastUnlockOperationSensor(self.coordinator, self.mock_entry)
        last_lock_sensor = Sesame5LastLockOperationSensor(self.coordinator, self.mock_entry)
        door_sensor = Sesame5DoorBinarySensor(self.coordinator, self.mock_entry)
        lock = Sesame5BleLock(self.coordinator, self.mock_entry)

        # 1. Keypad Fingerprint unlock (HistoryType.BLE_UNLOCK=2, tag=FINGERPRINT=1)
        # raw: result(1B)=0, record_id(4B)=201, type(1B)=2, timestamp(4B), mech(7B), tag_data: len(1B)=0, type(1B)=1 (FINGERPRINT), 16B UUID
        tag_data = struct.pack("<BB16s", 0, HistoryTagType.FINGERPRINT.value, b"\x22" * 16)
        fp_payload = struct.pack("<BiBI7s", 0, 201, HistoryType.BLE_UNLOCK.value, 1732000200, b"\x00" * 7) + tag_data
        fp_record = Sesame5HistoryRecord(fp_payload)
        self.assertEqual(fp_record.description_zh, "门外指纹解锁")
        self.assertEqual(fp_record.source, "outside")
        self.assertIsNone(fp_record.door_open)

        self.device._process_history_record(fp_record)
        self.device._mech_status = Sesame5MechStatus(struct.pack("<HhhB", 3000, 0, 200, 0x14))
        self.coordinator.data = self.coordinator._current_state

        self.assertEqual(last_op_sensor.native_value, "门外指纹解锁")
        self.assertEqual(last_unlock_sensor.native_value, "门外指纹解锁")
        self.assertIsNone(last_lock_sensor.native_value)
        self.assertIsNone(door_sensor.is_on)

        # 2. BLE/App Lock (HistoryType.BLE_LOCK = 1)
        ble_lock_payload = struct.pack("<BiBI7sB", 0, 202, HistoryType.BLE_LOCK.value, 1732000250, b"\x00" * 7, 0)
        ble_lock_record = Sesame5HistoryRecord(ble_lock_payload)
        self.assertEqual(ble_lock_record.description_zh, "蓝牙/App 上锁")
        self.assertIsNone(ble_lock_record.door_open)

        self.device._process_history_record(ble_lock_record)
        self.device._mech_status = Sesame5MechStatus(struct.pack("<HhhB", 3000, 0, 90, 0x12))
        self.coordinator.data = self.coordinator._current_state

        self.assertEqual(last_op_sensor.native_value, "蓝牙/App 上锁")
        self.assertEqual(last_lock_sensor.native_value, "蓝牙/App 上锁")
        self.assertEqual(last_unlock_sensor.native_value, "门外指纹解锁")  # preserved
        self.assertIsNone(door_sensor.is_on)

    def test_subsequent_pairing_of_door_sensor(self):
        """Test seamless transition if a user later purchases and pairs an Open Sensor."""
        door_sensor = Sesame5DoorBinarySensor(self.coordinator, self.mock_entry)
        last_op_sensor = Sesame5LastOperationSensor(self.coordinator, self.mock_entry)
        last_unlock_sensor = Sesame5LastUnlockOperationSensor(self.coordinator, self.mock_entry)
        last_lock_sensor = Sesame5LastLockOperationSensor(self.coordinator, self.mock_entry)

        # Step 1: Lock operates standalone without door sensor
        self.assertIsNone(door_sensor.is_on)

        # Step 2: User adds Open Sensor, door opens (0x5A)
        # 24-byte tag layout for Open Sensor: [0, 7, 16B UUID, 2B volt1, 2B volt2, 1B cmd (0x5A), 1B 0xff]
        os_open_tag = struct.pack("<BB16sHHBB", 0, HistoryTagType.OPEN_SENSOR.value, b"\x99" * 16, 3000, 3000, 0x5A, 0xFF)
        os_open_payload = struct.pack("<BiBI7s", 0, 301, 0, 1732000300, b"\x00" * 7) + os_open_tag
        os_open_record = Sesame5HistoryRecord(os_open_payload)

        self.assertTrue(os_open_record.door_open)
        self.assertFalse(os_open_record.is_lock_operation)  # Must NOT update lock operation!

        self.device._process_history_record(os_open_record)
        self.coordinator.data = self.coordinator._current_state

        # Door binary sensor now becomes True ("on" / 打开)
        self.assertTrue(door_sensor.is_on)
        self.assertTrue(self.device.door_open)

        # Step 3: Door closes, auto-lock triggers (0x5B)
        os_close_tag = struct.pack("<BB16sHHBB", 0, HistoryTagType.OPEN_SENSOR.value, b"\x99" * 16, 3000, 3000, 0x5B, 0xFF)
        os_close_payload = struct.pack("<BiBI7s", 0, 302, 0, 1732000310, b"\x00" * 7) + os_close_tag
        os_close_record = Sesame5HistoryRecord(os_close_payload)

        self.assertFalse(os_close_record.door_open)
        self.assertTrue(os_close_record.is_lock_operation)  # Closing door with auto-lock IS a lock operation
        self.assertEqual(os_close_record.description_zh, "关门自动上锁")

        self.device._process_history_record(os_close_record)
        self.device._mech_status = Sesame5MechStatus(struct.pack("<HhhB", 3000, 0, 90, 0x12))
        self.coordinator.data = self.coordinator._current_state

        # Door binary sensor now becomes False ("off" / 关闭)
        self.assertFalse(door_sensor.is_on)
        self.assertFalse(self.device.door_open)
        self.assertEqual(last_op_sensor.native_value, "关门自动上锁")
        self.assertEqual(last_lock_sensor.native_value, "关门自动上锁")

    async def test_ha_restart_restoration_without_door_sensor(self):
        """Test HA restart cleanly restores sensors without falsely setting door_open."""
        door_sensor = Sesame5DoorBinarySensor(self.coordinator, self.mock_entry)
        last_op_sensor = Sesame5LastOperationSensor(self.coordinator, self.mock_entry)
        last_unlock_sensor = Sesame5LastUnlockOperationSensor(self.coordinator, self.mock_entry)
        last_lock_sensor = Sesame5LastLockOperationSensor(self.coordinator, self.mock_entry)

        # Coordinator data currently empty/initial
        self.coordinator.data = Sesame5State(
            mech_status=None,
            mech_settings=None,
            history=None,
            last_unlock_history=None,
            last_lock_history=None,
            door_open=None,
        )

        # Simulate door sensor previous state was "unknown" (because user has no door sensor)
        mock_unknown_state = MagicMock()
        mock_unknown_state.state = "unknown"

        with patch.object(door_sensor, "async_get_last_state", new_callable=AsyncMock) as mock_get_state:
            mock_get_state.return_value = mock_unknown_state
            await door_sensor.async_added_to_hass()

            # door_open must stay None
            self.assertIsNone(self.coordinator.device.door_open)
            self.assertIsNone(door_sensor.is_on)

        # Simulate operation sensors restoring their values
        mock_last_op_state = MagicMock()
        mock_last_op_state.state = "自动上锁"
        with patch.object(last_op_sensor, "async_get_last_state", new_callable=AsyncMock) as mock_get_state:
            mock_get_state.return_value = mock_last_op_state
            await last_op_sensor.async_added_to_hass()
            self.assertEqual(last_op_sensor.native_value, "自动上锁")

        mock_last_unlock_state = MagicMock()
        mock_last_unlock_state.state = "门内手动解锁"
        with patch.object(last_unlock_sensor, "async_get_last_state", new_callable=AsyncMock) as mock_get_state:
            mock_get_state.return_value = mock_last_unlock_state
            await last_unlock_sensor.async_added_to_hass()
            self.assertEqual(last_unlock_sensor.native_value, "门内手动解锁")

        mock_last_lock_state = MagicMock()
        mock_last_lock_state.state = "自动上锁"
        with patch.object(last_lock_sensor, "async_get_last_state", new_callable=AsyncMock) as mock_get_state:
            mock_get_state.return_value = mock_last_lock_state
            await last_lock_sensor.async_added_to_hass()
            self.assertEqual(last_lock_sensor.native_value, "自动上锁")

    async def test_dynamic_visibility_synchronization(self):
        """Test entity registry visibility lifecycle for door sensor."""
        from tests import mock_entity_registry, MockRegistryEntry
        from homeassistant.helpers import entity_registry as er
        from custom_components.sesame5_ble.const import DOMAIN

        door_sensor = Sesame5DoorBinarySensor(self.coordinator, self.mock_entry)
        door_sensor.entity_id = "binary_sensor.test_door"
        reg_entry = MockRegistryEntry(door_sensor.entity_id, hidden_by=None)
        mock_entity_registry.entities[door_sensor.entity_id] = reg_entry

        # 1. No door sensor detected (coordinator data has door_open = None)
        self.coordinator.data = Sesame5State(
            mech_status=None,
            mech_settings=None,
            history=None,
            last_unlock_history=None,
            last_lock_history=None,
            door_open=None,
        )

        with patch.object(door_sensor, "async_get_last_state", new_callable=AsyncMock) as mock_get_state:
            mock_get_state.return_value = None
            await door_sensor.async_added_to_hass()

        # Must be hidden by integration and marked initialized
        self.assertEqual(reg_entry.hidden_by, er.RegistryEntryHider.INTEGRATION)
        self.assertTrue(reg_entry.options[DOMAIN]["visibility_initialized"])

        # 2. User manually unhides entity in HA Settings
        reg_entry.hidden_by = None
        # Subsequent update without door sensor must NOT re-hide it
        door_sensor._sync_visibility()
        self.assertIsNone(reg_entry.hidden_by)

        # 3. User later adds Open Sensor (door_open becomes True)
        # First reset hidden_by back to INTEGRATION to test unhiding
        reg_entry.hidden_by = er.RegistryEntryHider.INTEGRATION
        self.device.set_door_open(True)
        self.coordinator.data = self.coordinator._current_state
        door_sensor._handle_coordinator_update()

        # Must be automatically unhidden!
        self.assertIsNone(reg_entry.hidden_by)


if __name__ == "__main__":
    unittest.main()
