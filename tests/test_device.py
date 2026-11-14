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


if __name__ == "__main__":
    unittest.main()
