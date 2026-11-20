"""Unit tests for simulated real-life Bluetooth data and poor-signal robustness scenarios.

Tests include:
1. Replaying exact raw payloads extracted from live Home Assistant logs.
2. Truncated, malformed, and partial BLE data packets caused by signal attenuation.
3. Dropped packet chunks, orphan fragments, and buffer overflow recovery.
4. AES-CCM sliding window resynchronization under dropped BLE notifications.
5. Sudden BLE disconnection during pending command requests.
6. Keypad timeout handling on empty credential streams (e.g. 0 registered cards).
"""

import asyncio
import struct
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import tests  # Preload HA mock environment
from custom_components.sesame5_ble.const import (
    HistoryTagType,
    HistoryType,
    ItemCode,
    PacketType,
    ResultCode,
)
from custom_components.sesame5_ble.crypto import OS3Cipher, generate_session_key
from custom_components.sesame5_ble.device import STATE_READY, Sesame5Device
from custom_components.sesame5_ble.helpers import (
    BleFrameReceiver,
    BleFrameTransmitter,
    Sesame5HistoryRecord,
    Sesame5MechSetting,
    Sesame5MechStatus,
    parse_credential_records,
)


class TestSignalRobustness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_hass = MagicMock()
        self.address = "D7:E9:5F:21:34:A8"
        self.secret_key = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")
        self.device = Sesame5Device(self.address, self.secret_key, self.mock_hass)
        self.device._client = MagicMock(is_connected=True)
        self.device._state = STATE_READY

    def test_real_ha_log_data_replay(self):
        """Replay exact status, setting, and history payloads recorded in real HA logs."""
        # 1. Real MECH_SETTING from log: lock_pos=66, unlock_pos=216, autolock=0s
        setting_payload = struct.pack("<hhH", 66, 216, 0)
        settings = Sesame5MechSetting(setting_payload)
        self.assertEqual(settings.lock_position, 66)
        self.assertEqual(settings.unlock_position, 216)
        self.assertEqual(settings.auto_lock_duration, 0)
        self.assertTrue(settings.is_configured)

        # 2. Real MECH_STATUS from log: locked=True, pos=68, target=-32768, batt=100% (5.98V)
        # raw_battery = 5.98 * 1000 / 2 = 2990
        # flags = IS_IN_LOCK_RANGE (0x02) | IS_STOP (0x10) = 0x12
        status_payload = struct.pack("<HhhB", 2990, -32768, 68, 0x12)
        status = Sesame5MechStatus(status_payload)
        self.assertEqual(status.battery_voltage, 5.98)
        self.assertEqual(status.battery_percentage, 100)
        self.assertEqual(status.position, 68)
        self.assertTrue(status.is_locked())

        # 3. Real Candy House Open Sensor door-close auto-lock history payload from log
        # (result=0x00, tag=OPEN_SENSOR, action=lock, time=2026-11-19T10:13:05+00:00)
        live_os_close = bytes.fromhex(
            "00540000000194b8f96abf0b4200d500540007112005090108080457005c00ffffffffc40ab90a5bff"
        )
        record = Sesame5HistoryRecord(live_os_close)
        self.device._process_history_record(record)

        self.assertEqual(self.device.history.description_zh, "关门自动上锁")
        self.assertEqual(self.device.history.action, "lock")
        self.assertEqual(self.device.last_lock_history.description_zh, "关门自动上锁")
        self.assertIsNone(self.device.last_unlock_history)
        self.assertFalse(self.device.door_open)

    async def test_truncated_and_partial_payloads(self):
        """Simulate packets truncated mid-air due to weak RF signal."""
        # 1. Truncated MECH_STATUS (0 or 1 byte instead of >= 2)
        with self.assertRaises(ValueError):
            Sesame5MechStatus(b"")
        with self.assertRaises(ValueError):
            Sesame5MechStatus(b"\x01")

        # 2. Truncated MECH_SETTING (< 6 bytes)
        with self.assertRaises(ValueError):
            Sesame5MechSetting(b"\x01\x02\x03")

        # 3. Truncated HISTORY record (< 17 bytes)
        with self.assertRaises(ValueError):
            Sesame5HistoryRecord(b"\x00\x01\x02\x03\x04\x05")

        # 4. Truncated Keypad Credential Notify record (packet cut off in the middle of a record)
        # Record format: card_type(1B), id_len(1B), id, name_len(1B), name
        # Valid header but id_len claims 10 bytes while only 3 exist
        truncated_cred_payload = bytes([0x00, 10, 0x01, 0x02, 0x03])
        records = parse_credential_records(truncated_cred_payload)
        self.assertEqual(records, [])  # Safely discards truncated record without raising IndexError

        # Partial valid record followed by truncated record
        valid_part = bytes([0x00, 4, 1, 2, 3, 4, 4]) + b"User"
        partial_part = bytes([0x00, 8, 1, 2])  # Incomplete
        combined = valid_part + partial_part
        records2 = parse_credential_records(combined)
        self.assertEqual(len(records2), 1)
        self.assertEqual(records2[0]["name"], "User")

    def test_packet_fragmentation_loss_and_overflow(self):
        """Test receiver robustness when BLE chunks are lost or disordered."""
        rx = BleFrameReceiver()

        # 1. Orphan continuation chunks (beginning packet was lost over the air)
        is_enc, data = rx.feed(bytes([0x00]) + b"orphan_middle_chunk")
        self.assertIsNone(is_enc)
        self.assertIsNone(data)
        self.assertEqual(len(rx._buffer), 0)  # Must not store corrupt orphan chunk

        # 2. Runaway corrupted stream without END packet (buffer overflow protection)
        rx.feed(bytes([PacketType.BEGINNING]) + b"A" * 15)
        self.assertEqual(len(rx._buffer), 15)

        # Feed packets exceeding MAX_BUFFER_SIZE (512 bytes)
        for _ in range(35):
            rx.feed(bytes([0x00]) + b"B" * 18)

        # Buffer must have been reset to 0 to prevent runaway memory usage
        self.assertEqual(len(rx._buffer), 0)

        # 3. Fresh valid packet arriving after buffer reset completes normally
        rx.feed(bytes([PacketType.BEGINNING]) + b"CleanStart")
        is_enc, clean_data = rx.feed(bytes([PacketType.PLAINTEXT_END]) + b"CleanEnd")
        self.assertFalse(is_enc)
        self.assertEqual(clean_data, b"CleanStartCleanEnd")

    def test_dropped_notification_sliding_window_resync(self):
        """Test AES-CCM sliding window recovery when a notification packet is dropped."""
        session_token = bytes.fromhex("b99bd638")
        session_key = generate_session_key(self.secret_key, session_token)
        cipher_sender = OS3Cipher(session_token, session_key)
        cipher_receiver = OS3Cipher(session_token, session_key)

        # Packet 0: normal transmission
        pkt0 = cipher_sender.encrypt(b"Packet_0")
        dec0 = cipher_receiver.decrypt(pkt0)
        self.assertEqual(dec0, b"Packet_0")

        # Packet 1 is DROPPED by BLE channel (sender encrypts it, receiver never gets it)
        _ = cipher_sender.encrypt(b"Packet_1_lost")

        # Packet 2 arrives at receiver (counter 1 was dropped, counter 2 received)
        pkt2 = cipher_sender.encrypt(b"Packet_2")
        dec2 = cipher_receiver.decrypt(pkt2)
        # Sliding window must seamlessly recover and resynchronize counter
        self.assertEqual(dec2, b"Packet_2")
        self.assertEqual(cipher_receiver._decrypt_counter, 3)

    async def test_sudden_disconnection_during_command(self):
        """Test command future cleanup and state reset if BLE disconnects mid-flight."""
        # 1. request_history awaiting response when disconnect happens
        with patch.object(self.device, "send_command", new_callable=AsyncMock) as mock_send:
            # Simulate send_command raising CancelledError when connection drops
            mock_send.side_effect = asyncio.CancelledError()

            record = await self.device.request_history()
            self.assertIsNone(record)
            # Flag must be reset to False even on CancelledError
            self.assertFalse(self.device._history_in_progress)

        # 2. send_command future cleanup on timeout
        with patch.object(self.device, "_transmit", new_callable=AsyncMock):
            with patch("custom_components.sesame5_ble.device.COMMAND_TIMEOUT", 0.05):
                with self.assertRaises(asyncio.TimeoutError):
                    await self.device.send_command(ItemCode.LOCK, b"", is_encrypted=False)

            # Dictionary must be completely empty (cleaned up in finally block)
            self.assertEqual(len(self.device._command_response_futures), 0)

    async def test_keypad_empty_credential_timeout_graceful(self):
        """Simulate real log scenario: Keypad has 0 cards registered, CARD_GET times out gracefully."""
        # When Keypad has 0 cards, it returns SUCCESS response to CARD_GET, but sends no card notify stream
        self.device._model_id = 9  # Touch device
        with patch.object(self.device, "send_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = (ResultCode.SUCCESS, b"")
            # Set a very short timeout for testing
            cards = await self.device.request_cards(timeout=0.05)
            self.assertEqual(cards, [])
            self.assertEqual(self.device.card_count, 0)


if __name__ == "__main__":
    unittest.main()
