"""Unit tests for Sesame 5 device communication logic and handshake."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import tests  # Preload mock stubs
from custom_components.sesame5_ble.const import (
    DEFAULT_HISTORY_TAG,
    ItemCode,
    OpCode,
    ResultCode,
)
from custom_components.sesame5_ble.device import Sesame5Device
from custom_components.sesame5_ble.helpers import BleFrameTransmitter, create_history_tag


class TestSesame5Device(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_hass = MagicMock()
        self.address = "AA:BB:CC:DD:EE:FF"
        self.secret_key = bytes(range(16))
        self.device = Sesame5Device(self.address, self.secret_key, self.mock_hass)

    def test_initialization(self):
        self.assertEqual(self.device.address, self.address)
        self.assertFalse(self.device.is_connected)
        self.assertFalse(self.device.is_ready)
        self.assertIsNone(self.device.mech_status)
        self.assertIsNone(self.device.mech_settings)

    async def test_handle_initial_token_publish(self):
        token = b"\x01\x02\x03\x04"
        await self.device._handle_publish(ItemCode.INITIAL.value, token)
        self.assertEqual(self.device._session_token, token)
        self.assertTrue(self.device._initial_token_received.is_set())

    async def test_handle_mech_status_publish(self):
        # 7 bytes MECH_STATUS payload
        import struct

        payload = struct.pack("<HhhB", 2900, 0, 90, 0x12)
        callback_called = False

        def on_update():
            nonlocal callback_called
            callback_called = True

        self.device.add_update_callback(on_update)
        await self.device._handle_publish(ItemCode.MECH_STATUS.value, payload)

        self.assertIsNotNone(self.device.mech_status)
        self.assertEqual(self.device.mech_status.battery_voltage, 5.8)
        self.assertTrue(callback_called)

    async def test_handle_login_response_success(self):
        await self.device._handle_response(ItemCode.LOGIN.value, ResultCode.SUCCESS.value, b"")
        self.assertTrue(self.device._logged_in.is_set())

    async def test_handle_login_response_failure(self):
        await self.device._handle_response(ItemCode.LOGIN.value, ResultCode.INVALID_SIG.value, b"")
        self.assertFalse(self.device._logged_in.is_set())

    async def test_lock_state_change_tracking_across_moving_state(self):
        import struct
        from custom_components.sesame5_ble.device import STATE_READY

        self.device._client = MagicMock(is_connected=True)
        self.device._state = STATE_READY

        # 1. Start locked (pos 66, IS_STOP | IS_IN_LOCK_RANGE = 0x12)
        locked_payload = struct.pack("<HhhB", 3000, 0, 66, 0x12)
        await self.device._handle_publish(ItemCode.MECH_STATUS.value, locked_payload)
        self.assertTrue(self.device.mech_status.is_locked())
        self.assertTrue(self.device._last_known_locked)

        # 2. Motor starts moving (pos 140, indeterminate None, IS_CLOCKWISE = 0x40)
        moving_payload = struct.pack("<HhhB", 3000, 0, 140, 0x40)
        await self.device._handle_publish(ItemCode.MECH_STATUS.value, moving_payload)
        self.assertIsNone(self.device.mech_status.is_locked())
        # _last_known_locked must persist as True so state transition is preserved
        self.assertTrue(self.device._last_known_locked)

        # 3. Motor reaches unlocked (pos 216, IS_STOP | IS_IN_UNLOCK_RANGE = 0x14)
        with patch.object(self.device, "request_history", new_callable=AsyncMock) as mock_hist:
            mock_hist.return_value = None
            unlocked_payload = struct.pack("<HhhB", 3000, 0, 216, 0x14)
            await self.device._handle_publish(ItemCode.MECH_STATUS.value, unlocked_payload)
            self.assertFalse(self.device.mech_status.is_locked())
            self.assertFalse(self.device._last_known_locked)
            # Give background task event loop a turn
            await asyncio.sleep(0.01)
            # request_history must be called to sync history before HA automation fires
            mock_hist.assert_called_once()

    async def test_open_sensor_door_open_preserves_unlock_history(self):
        import struct
        from custom_components.sesame5_ble.device import STATE_READY
        from custom_components.sesame5_ble.helpers import Sesame5HistoryRecord

        self.device._client = MagicMock(is_connected=True)
        self.device._state = STATE_READY

        # Simulate existing fingerprint unlock history
        fp_payload = struct.pack("<BiBI7sBB16s", 0, 109, 2, 1731580000, b"\x00" * 7, 0, 1, b"\x11" * 16)
        fp_record = Sesame5HistoryRecord(fp_payload)
        self.device._process_history_record(fp_record)
        self.assertEqual(self.device.history.description_zh, "门外指纹解锁")
        self.assertEqual(self.device.last_unlock_history.description_zh, "门外指纹解锁")
        self.assertIsNone(self.device.last_lock_history)

        # 1. Simulate receiving an Open Sensor door-opening event (0x5A)
        os_open_payload = bytes.fromhex("00540000000194b8f96abf0b4200d500540007112005090108080457005c00ffffffffc40ab90a5aff")

        with patch.object(self.device, "send_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = (ResultCode.SUCCESS, os_open_payload[1:])
            record = await self.device.request_history()

            self.assertIsNotNone(record)
            # Door sensor must update door state to open
            self.assertTrue(self.device.door_open)
            # BUT _history & _last_unlock_history must NOT be overwritten by door-opening event!
            self.assertEqual(self.device.history.description_zh, "门外指纹解锁")
            self.assertEqual(self.device.history.source, "outside")
            self.assertEqual(self.device.last_unlock_history.description_zh, "门外指纹解锁")
            self.assertIsNone(self.device.last_lock_history)

        # 2. Simulate receiving an Open Sensor door-closing auto-lock event (0x5B)
        os_close_payload = bytes.fromhex("00540000000194b8f96abf0b4200d500540007112005090108080457005c00ffffffffc40ab90a5bff")
        with patch.object(self.device, "send_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = (ResultCode.SUCCESS, os_close_payload[1:])
            record_close = await self.device.request_history()

            self.assertIsNotNone(record_close)
            # Door sensor updates door state to closed
            self.assertFalse(self.device.door_open)
            # "关门自动上锁" IS a lock operation -> updates last_operation AND last_lock_operation
            self.assertEqual(self.device.history.description_zh, "关门自动上锁")
            self.assertEqual(self.device.last_lock_history.description_zh, "关门自动上锁")
            # BUT last_unlock_history STILL preserves the fingerprint unlock!
            self.assertEqual(self.device.last_unlock_history.description_zh, "门外指纹解锁")

    async def test_lifecycle_disconnect_and_history_clean(self):
        """Test disconnect and history calls do not raise NameError or create lingering tasks."""
        # 1. request_history returns None (empty / failure)
        with patch.object(self.device, "send_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = (ResultCode.NOT_FOUND, b"")
            record = await self.device.request_history()
            self.assertIsNone(record)
            self.assertFalse(self.device._history_in_progress)

        # 2. _on_disconnect cleans up properly
        self.device._on_disconnect(MagicMock())
        self.assertFalse(self.device.is_connected)
        self.assertFalse(self.device._history_in_progress)

        # 3. disconnect cleans up properly
        await self.device.disconnect()
        self.assertFalse(self.device.is_connected)
        self.assertFalse(self.device._history_in_progress)


if __name__ == "__main__":
    unittest.main()
