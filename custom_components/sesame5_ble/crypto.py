"""Cryptographic primitives for SesameOS 3 BLE protocol.

Implements AES-CMAC session key derivation and AES-CCM authenticated encryption/decryption
using standard Python `cryptography` library.
"""

from __future__ import annotations

import logging
from cryptography.hazmat.primitives import cmac
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

LOGGER = logging.getLogger(__name__)


def generate_session_key(secret_key: bytes, session_token: bytes) -> bytes:
    """Compute 16-byte session key from device secret key and 4-byte session token using AES-CMAC.

    Args:
        secret_key: 16-byte shared secret key.
        session_token: 4-byte token received from lock via INITIAL publish.

    Returns:
        16-byte session key.
    """
    if len(secret_key) != 16:
        raise ValueError(f"Secret key must be 16 bytes, got {len(secret_key)}")
    if len(session_token) != 4:
        raise ValueError(f"Session token must be 4 bytes, got {len(session_token)}")

    c = cmac.CMAC(algorithms.AES(secret_key))
    c.update(session_token)
    return c.finalize()


class OS3Cipher:
    """AES-CCM cipher manager for SesameOS 3 BLE session."""

    _MAX_COUNTER = 2**64 - 1

    def __init__(self, session_token: bytes, session_key: bytes) -> None:
        """Initialize cipher with session token and session key."""
        if len(session_token) != 4:
            raise ValueError(f"Session token must be 4 bytes, got {len(session_token)}")
        if len(session_key) != 16:
            raise ValueError(f"Session key must be 16 bytes, got {len(session_key)}")

        self._session_token = session_token
        self._session_key = session_key
        self._encrypt_counter = 0
        self._decrypt_counter = 0
        self._aesccm = AESCCM(key=self._session_key, tag_length=4)

    def _generate_nonce(self, counter: int) -> bytes:
        """Construct a 13-byte nonce from 64-bit counter and session token.

        Format: [counter (8 bytes little-endian)] + [0x00] + [session_token (4 bytes)]
        """
        return counter.to_bytes(8, "little") + b"\x00" + self._session_token

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt plaintext using AES-CCM with a 4-byte MAC.

        Args:
            plaintext: Plain bytes to encrypt.

        Returns:
            Ciphertext with appended 4-byte MAC tag.
        """
        if self._encrypt_counter >= self._MAX_COUNTER:
            raise OverflowError("Encryption counter overflow")

        nonce = self._generate_nonce(self._encrypt_counter)
        self._encrypt_counter += 1
        return self._aesccm.encrypt(nonce=nonce, data=plaintext, associated_data=b"\x00")

    def decrypt(self, ciphertext: bytes, window: int = 5) -> bytes:
        """Decrypt ciphertext and verify the 4-byte MAC using AES-CCM.

        Only advances decrypt counter upon successful decryption. If the current
        counter fails, probes a small forward window (up to `window` positions) to
        seamlessly recover from dropped BLE packets. If verification still fails,
        the decrypt counter is left unchanged so future valid packets can still succeed.

        Args:
            ciphertext: Encrypted bytes including trailing 4-byte MAC tag.
            window: Maximum number of dropped packets to probe ahead.

        Returns:
            Decrypted plaintext bytes.

        Raises:
            cryptography.exceptions.InvalidTag: If MAC tag validation fails.
        """
        if self._decrypt_counter >= self._MAX_COUNTER:
            raise OverflowError("Decryption counter overflow")

        # 1. Try current expected counter
        nonce = self._generate_nonce(self._decrypt_counter)
        try:
            plaintext = self._aesccm.decrypt(nonce=nonce, data=ciphertext, associated_data=b"\x00")
            self._decrypt_counter += 1
            return plaintext
        except Exception:
            pass

        # 2. Probe forward window in case 1..window packets were dropped over BLE
        for skip in range(1, window + 1):
            candidate = self._decrypt_counter + skip
            if candidate >= self._MAX_COUNTER:
                break
            nonce = self._generate_nonce(candidate)
            try:
                plaintext = self._aesccm.decrypt(nonce=nonce, data=ciphertext, associated_data=b"\x00")
                LOGGER.warning(
                    "Recovered from %d dropped BLE packet(s) (decrypt counter resynced: %d -> %d)",
                    skip,
                    self._decrypt_counter,
                    candidate + 1,
                )
                self._decrypt_counter = candidate + 1
                return plaintext
            except Exception:
                continue

        # 3. None matched: raise InvalidTag without advancing the counter
        from cryptography.exceptions import InvalidTag
        raise InvalidTag("Failed to decrypt notification; MAC verification failed")
