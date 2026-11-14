"""Mock Home Assistant, Bleak, and Cryptography modules for standalone unit testing."""

import sys
from unittest.mock import MagicMock

for mod in [
    "homeassistant",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.data_entry_flow",
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
    "homeassistant.helpers.dispatcher",
    "homeassistant.helpers.event",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.selector",
    "voluptuous",
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

sys.modules["homeassistant.const"].CONF_ADDRESS = "address"


class MockDataUpdateCoordinator:
    def __init__(self, hass, logger, name, config_entry, update_interval=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.config_entry = config_entry
        self.update_interval = update_interval
        self.data = None

    def __class_getitem__(cls, item):
        return cls

    def async_set_updated_data(self, data):
        self.data = data


sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = MockDataUpdateCoordinator
