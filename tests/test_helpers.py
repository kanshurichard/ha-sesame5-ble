"""Unit tests for helpers: QR decoding, packet framing, status parsing, battery calculation."""

import base64
import struct
import unittest
from uuid import UUID

import tests  # Preload mock stubs for homeassistant/bleak

from custom_components.sesame5_ble.const import (
    HistoryTagType,
    HistoryType,
    ItemCode,
    MechStatusBitFlag,
    PacketType,
    ProductModel,
)
from custom_components.sesame5_ble.helpers import (
    BleFrameReceiver,
    BleFrameTransmitter,
    Sesame5HistoryRecord,
    Sesame5MechSetting,
    Sesame5MechStatus,
    calculate_battery_percentage,
    create_history_tag,
    parse_secret_key_input,
)


class TestHelpers(unittest.TestCase):
    def test_battery_percentage_calculation(self):
        # 6.0V -> 100%
        self.assertEqual(calculate_battery_percentage(6.0), 100)
        # 4.5V -> 0%
        self.assertEqual(calculate_battery_percentage(4.5), 0)
        # 5.85V -> 100%
        self.assertEqual(calculate_battery_percentage(5.85), 100)
        # 4.60V -> 0%
        self.assertEqual(calculate_battery_percentage(4.60), 0)
        # Between 5.85 and 5.82 -> interpolated
        val = calculate_battery_percentage(5.835)
        self.assertEqual(val, 97)

    def test_create_history_tag(self):
        # Normal tag
        tag = create_history_tag("HA")
        self.assertEqual(tag, b"\x02HA")

        # Empty tag
        self.assertEqual(create_history_tag(""), b"\x00")

        # Long tag truncated to 20 bytes
        long_tag = "A" * 30
        res = create_history_tag(long_tag)
        self.assertEqual(res, b"\x14" + b"A" * 20)

    def test_parse_secret_key_input(self):
        # Hex string
        hex_key = "0102030405060708090a0b0c0d0e0f10"
        sk, uuid_str, model_id = parse_secret_key_input(hex_key)
        self.assertEqual(sk, bytes.fromhex(hex_key))
        self.assertIsNone(uuid_str)
        self.assertIsNone(model_id)

        # OS3 QR URL
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        shared_key = struct.pack(
            ">B16s4s2s16s",
            ProductModel.SESAME_5.value,
            b"\xaa" * 16,
            b"\xbb" * 4,
            b"\x00\x01",
            test_uuid.bytes,
        )
        sk_b64 = base64.b64encode(shared_key).decode("ascii")
        qr_url = f"ssm://UI?t=sk&sk={sk_b64}&l=0&n=Front+Door"

        sk, uuid_str, model_id = parse_secret_key_input(qr_url)
        self.assertEqual(sk, b"\xaa" * 16)
        self.assertEqual(uuid_str, str(test_uuid))
        self.assertEqual(model_id, 5)

        # Direct Base64 string (39 bytes)
        sk2, uuid_str2, model_id2 = parse_secret_key_input(sk_b64)
        self.assertEqual(sk2, b"\xaa" * 16)
        self.assertEqual(uuid_str2, str(test_uuid))
        self.assertEqual(model_id2, 5)

    def test_mech_status_parsing(self):
        # <HhhB: raw_battery(2B), target(2B), position(2B), flags(1B)
        # raw_battery = 2925 -> 2925 * 2 / 1000 = 5.85V -> 100%
        # target = 0, position = 90
        # flags = IS_IN_LOCK_RANGE (0x02) | IS_STOP (0x10) = 0x12
        payload = struct.pack("<HhhB", 2925, 0, 90, 0x12)
        status = Sesame5MechStatus(payload)

        self.assertEqual(status.battery_voltage, 5.85)
        self.assertEqual(status.battery_percentage, 100)
        self.assertEqual(status.target_position, 0)
        self.assertEqual(status.position, 90)
        self.assertTrue(status.is_in_lock_range)
        self.assertFalse(status.is_in_unlock_range)
        self.assertTrue(status.is_stop)
        self.assertFalse(status.is_battery_critical)
        self.assertEqual(status.is_locked(), True)

        # Unlock range test
        # flags = IS_IN_UNLOCK_RANGE (0x04)
        payload_unlock = struct.pack("<HhhB", 2500, 180, 180, 0x04)
        status_unlock = Sesame5MechStatus(payload_unlock)
        self.assertEqual(status_unlock.is_locked(), False)

    def test_mech_setting_parsing(self):
        # <hhH: lock_pos, unlock_pos, auto_lock
        payload = struct.pack("<hhH", 90, 0, 15)
        setting = Sesame5MechSetting(payload)
        self.assertEqual(setting.lock_position, 90)
        self.assertEqual(setting.unlock_position, 0)
        self.assertEqual(setting.auto_lock_duration, 15)
        self.assertTrue(setting.is_configured)

    def test_ble_framing_roundtrip(self):
        # Small plaintext message (single packet)
        msg = b"\x02\x01\x02\x03\x04"
        tx = BleFrameTransmitter(msg, is_encrypted=False)
        chunk = tx.get_chunk()
        self.assertIsNotNone(chunk)
        self.assertIsNone(tx.get_chunk())

        rx = BleFrameReceiver()
        is_enc, received = rx.feed(chunk)
        self.assertFalse(is_enc)
        self.assertEqual(received, msg)

        # Large encrypted message (multiple packets)
        long_msg = bytes(range(45))
        tx_enc = BleFrameTransmitter(long_msg, is_encrypted=True)
        rx_enc = BleFrameReceiver()

        final_msg = None
        final_enc = None
        while True:
            c = tx_enc.get_chunk()
            if c is None:
                break
            is_e, data = rx_enc.feed(c)
            if data is not None:
                final_enc = is_e
                final_msg = data

        self.assertTrue(final_enc)
        self.assertEqual(final_msg, long_msg)

    def test_history_record_parsing(self):
        # Format: [result(1B), record_id(4B), type(1B), timestamp(4B), mecha_status(7B), tag_data...]
        # 1. Manual inside unlock (type=8)
        data_manual = struct.pack("<BiBI7sB", 0, 101, 8, 1731580000, b"\x00" * 7, 0)
        hist_manual = Sesame5HistoryRecord(data_manual)
        self.assertEqual(hist_manual.action, "unlock")
        self.assertEqual(hist_manual.source, "inside")
        self.assertEqual(hist_manual.description_zh, "门内手动解锁")

        # 2. Manual inside lock (type=7)
        data_lock = struct.pack("<BiBI7sB", 0, 102, 7, 1731580000, b"\x00" * 7, 0)
        hist_lock = Sesame5HistoryRecord(data_lock)
        self.assertEqual(hist_lock.action, "lock")
        self.assertEqual(hist_lock.source, "inside")
        self.assertEqual(hist_lock.description_zh, "门内手动上锁")

        # 3. Auto-lock (type=6)
        data_auto = struct.pack("<BiBI7sB", 0, 103, 6, 1731580000, b"\x00" * 7, 0)
        hist_auto = Sesame5HistoryRecord(data_auto)
        self.assertEqual(hist_auto.action, "lock")
        self.assertEqual(hist_auto.source, "auto")
        self.assertEqual(hist_auto.description_zh, "自动上锁")

        # 4. Fingerprint unlock via accessory (type=2, tag_len=0, tag_type=1)
        data_fp = struct.pack("<BiBI7sBB16s", 0, 104, 2, 1731580000, b"\x00" * 7, 0, 1, b"\x11" * 16)
        hist_fp = Sesame5HistoryRecord(data_fp)
        self.assertEqual(hist_fp.action, "unlock")
        self.assertEqual(hist_fp.source, "outside")
        self.assertEqual(hist_fp.description_zh, "门外指纹解锁")

        # 5. Password unlock via keypad (type=2, tag_len=0, tag_type=2)
        data_pw = struct.pack("<BiBI7sBB16s", 0, 105, 2, 1731580000, b"\x00" * 7, 0, 2, b"\x22" * 16)
        hist_pw = Sesame5HistoryRecord(data_pw)
        self.assertEqual(hist_pw.description_zh, "门外密码解锁")

        # 6. Bluetooth App unlock with name tag "HA"
        tag_bytes = b"HA"
        data_ble = struct.pack("<BiBI7sB", 0, 106, 2, 1731580000, b"\x00" * 7, len(tag_bytes)) + tag_bytes
        hist_ble = Sesame5HistoryRecord(data_ble)
        self.assertEqual(hist_ble.action, "unlock")
        self.assertEqual(hist_ble.source, "app")
        self.assertEqual(hist_ble.tag_name, "HA")
        self.assertEqual(hist_ble.description_zh, "蓝牙/App 解锁 (HA)")


if __name__ == "__main__":
    unittest.main()
