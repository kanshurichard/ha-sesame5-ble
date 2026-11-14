"""Mock Home Assistant, Bleak, and Cryptography modules for standalone unit testing."""

import sys
from unittest.mock import MagicMock

for mod in [
    "homeassistant",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.exceptions",
    "homeassistant.components",
    "homeassistant.components.lock",
    "homeassistant.components.sensor",
    "homeassistant.components.binary_sensor",
    "homeassistant.components.bluetooth",
    "homeassistant.helpers",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.selector",
    "bleak",
    "bleak.backends",
    "bleak.backends.device",
    "bleak.backends.characteristic",
    "bleak_retry_connector",
    "cryptography",
    "cryptography.hazmat",
    "cryptography.hazmat.primitives",
    "cryptography.hazmat.primitives.cmac",
    "cryptography.hazmat.primitives.ciphers",
    "cryptography.hazmat.primitives.ciphers.algorithms",
    "cryptography.hazmat.primitives.ciphers.aead",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()
