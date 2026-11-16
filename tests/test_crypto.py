"""Unit tests for SesameOS 3 cryptographic operations and resync logic."""

import unittest
import tests  # Preload mock stubs
from cryptography.exceptions import InvalidTag
from custom_components.sesame5_ble.crypto import OS3Cipher, generate_session_key


class TestOS3Cipher(unittest.TestCase):
    def setUp(self):
        self.secret_key = bytes(range(16))
        self.session_token = b"\x01\x02\x03\x04"
        self.session_key = generate_session_key(self.secret_key, self.session_token)
        self.cipher = OS3Cipher(self.session_token, self.session_key)

    def test_encrypt_decrypt_normal(self):
        p0 = self.cipher.encrypt(b"hello world")
        p1 = self.cipher.encrypt(b"second packet")

        # Decrypt with fresh cipher simulating receiver
        recv_cipher = OS3Cipher(self.session_token, self.session_key)
        self.assertEqual(recv_cipher.decrypt(p0), b"hello world")
        self.assertEqual(recv_cipher.decrypt(p1), b"second packet")
        self.assertEqual(recv_cipher._decrypt_counter, 2)

    def test_recovery_from_dropped_packets(self):
        recv_cipher = OS3Cipher(self.session_token, self.session_key)

        p0 = self.cipher.encrypt(b"packet 0")
        p1 = self.cipher.encrypt(b"packet 1")  # Dropped!
        p2 = self.cipher.encrypt(b"packet 2")
        p3 = self.cipher.encrypt(b"packet 3")

        # Receive p0
        self.assertEqual(recv_cipher.decrypt(p0), b"packet 0")
        self.assertEqual(recv_cipher._decrypt_counter, 1)

        # p1 was lost in transmission! Receive p2 directly:
        self.assertEqual(recv_cipher.decrypt(p2), b"packet 2")
        self.assertEqual(recv_cipher._decrypt_counter, 3)

        # Receive p3 normally:
        self.assertEqual(recv_cipher.decrypt(p3), b"packet 3")
        self.assertEqual(recv_cipher._decrypt_counter, 4)

    def test_duplicate_packet_does_not_corrupt_counter(self):
        recv_cipher = OS3Cipher(self.session_token, self.session_key)

        p0 = self.cipher.encrypt(b"packet 0")
        p1 = self.cipher.encrypt(b"packet 1")

        # Receive p0
        self.assertEqual(recv_cipher.decrypt(p0), b"packet 0")
        self.assertEqual(recv_cipher._decrypt_counter, 1)

        # Duplicate p0 arrives again:
        with self.assertRaises(InvalidTag):
            recv_cipher.decrypt(p0)

        # Counter should remain 1 (NOT corrupted/advanced to 2)
        self.assertEqual(recv_cipher._decrypt_counter, 1)

        # Now real p1 arrives and succeeds
        self.assertEqual(recv_cipher.decrypt(p1), b"packet 1")
        self.assertEqual(recv_cipher._decrypt_counter, 2)

    def test_window_exceeded_raises_invalid_tag(self):
        recv_cipher = OS3Cipher(self.session_token, self.session_key)

        p0 = self.cipher.encrypt(b"packet 0")
        for _ in range(10):  # 10 dropped packets (window is 5)
            self.cipher.encrypt(b"intermediate")
        p_far = self.cipher.encrypt(b"far packet")

        self.assertEqual(recv_cipher.decrypt(p0), b"packet 0")
        with self.assertRaises(InvalidTag):
            recv_cipher.decrypt(p_far, window=5)


if __name__ == "__main__":
    unittest.main()
