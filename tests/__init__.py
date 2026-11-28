"""Mock Home Assistant, Bleak, and Cryptography modules for standalone unit testing."""

import sys
from unittest.mock import AsyncMock, MagicMock

# Try importing real cryptography if available, otherwise mock
try:
    import cryptography
    import cryptography.exceptions
    import cryptography.hazmat.primitives.ciphers.aead
    import cryptography.hazmat.primitives.cmac
    import cryptography.hazmat.primitives.ciphers.algorithms
except ImportError:
    for mod in [
        "cryptography",
        "cryptography.exceptions",
        "cryptography.hazmat",
        "cryptography.hazmat.primitives",
        "cryptography.hazmat.primitives.cmac",
        "cryptography.hazmat.primitives.ciphers",
        "cryptography.hazmat.primitives.ciphers.algorithms",
        "cryptography.hazmat.primitives.ciphers.aead",
    ]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

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
    "homeassistant.helpers.restore_state",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.selector",
    "homeassistant.helpers.service",
    "voluptuous",
    "bleak",
    "bleak.backends",
    "bleak.backends.device",
    "bleak.backends.characteristic",
    "bleak_retry_connector",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

sys.modules["homeassistant.const"].CONF_ADDRESS = "address"


class MockHomeAssistantError(Exception):
    pass


class MockConfigEntryNotReady(Exception):
    pass


sys.modules["homeassistant.exceptions"].HomeAssistantError = MockHomeAssistantError
sys.modules["homeassistant.exceptions"].ConfigEntryNotReady = MockConfigEntryNotReady


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

    async def async_config_entry_first_refresh(self):
        return None


class MockEntity:
    _attr_has_entity_name = False
    _attr_translation_key = None
    _attr_name = None
    _attr_unique_id = None

    @property
    def unique_id(self):
        return getattr(self, "_attr_unique_id", None)

    @property
    def translation_key(self):
        return getattr(self, "_attr_translation_key", None)

    @property
    def name(self):
        return getattr(self, "_attr_name", None)


class MockSensorEntity(MockEntity):
    pass


class MockBinarySensorEntity(MockEntity):
    pass


class MockLockEntity(MockEntity):
    pass


class MockRestoreEntity:
    async def async_added_to_hass(self):
        pass

    async def async_get_last_state(self):
        return None


class MockCoordinatorEntity(MockEntity):
    def __init__(self, coordinator=None):
        self.coordinator = coordinator
        self.hass = getattr(coordinator, "hass", None) if coordinator else None
        self.entity_id = f"binary_sensor.test_{getattr(self, '_attr_translation_key', 'entity')}"

    def __class_getitem__(cls, item):
        return cls

    def _handle_coordinator_update(self):
        pass

    def async_write_ha_state(self):
        pass


from enum import Enum


class MockRegistryEntryHider(str, Enum):
    INTEGRATION = "integration"
    USER = "user"


class MockRegistryEntry:
    def __init__(self, entity_id, hidden_by=None, options=None):
        self.entity_id = entity_id
        self.hidden_by = hidden_by
        self.options = options or {}


class MockEntityRegistry:
    def __init__(self):
        self.entities = {}

    def async_get(self, entity_id):
        return self.entities.get(entity_id)

    def async_update_entity(self, entity_id, *, hidden_by=None, **kwargs):
        if entity_id not in self.entities:
            self.entities[entity_id] = MockRegistryEntry(entity_id)
        entry = self.entities[entity_id]
        entry.hidden_by = hidden_by
        return entry

    def async_update_entity_options(self, entity_id, domain, options):
        if entity_id not in self.entities:
            self.entities[entity_id] = MockRegistryEntry(entity_id)
        entry = self.entities[entity_id]
        new_opts = dict(entry.options or {})
        if options is None:
            new_opts.pop(domain, None)
        else:
            new_opts[domain] = options
        entry.options = new_opts
        return entry


mock_entity_registry = MockEntityRegistry()
sys.modules["homeassistant.helpers.entity_registry"] = MagicMock()
sys.modules["homeassistant.helpers.entity_registry"].RegistryEntryHider = MockRegistryEntryHider
sys.modules["homeassistant.helpers.entity_registry"].async_get = MagicMock(return_value=mock_entity_registry)
sys.modules["homeassistant.helpers"].entity_registry = sys.modules["homeassistant.helpers.entity_registry"]
sys.modules["homeassistant.helpers"].service = sys.modules["homeassistant.helpers.service"]
sys.modules["homeassistant.helpers"].config_validation = sys.modules["homeassistant.helpers.config_validation"]
sys.modules["homeassistant.helpers"].device_registry = sys.modules["homeassistant.helpers.device_registry"]


sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = MockDataUpdateCoordinator
sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = MockCoordinatorEntity
sys.modules["homeassistant.components.sensor"].SensorEntity = MockSensorEntity
sys.modules["homeassistant.components.binary_sensor"].BinarySensorEntity = MockBinarySensorEntity
sys.modules["homeassistant.components.lock"].LockEntity = MockLockEntity
sys.modules["homeassistant.helpers.restore_state"].RestoreEntity = MockRestoreEntity


class MockOptionsFlow:
    def async_show_form(self, step_id=None, data_schema=None, errors=None, description_placeholders=None):
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors,
        }

    def async_create_entry(self, title="", data=None):
        return {"type": "create_entry", "title": title, "data": data}


class MockConfigFlow:
    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    async def async_set_unique_id(self, unique_id=None, raise_on_progress=True):
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self, updates=None, reload_on_update=True):
        pass

    def _async_current_ids(self, include_ignore=True):
        return set()

    def _async_current_entries(self, include_ignore=True):
        return []

    def async_show_form(self, step_id=None, data_schema=None, errors=None, description_placeholders=None):
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors,
        }

    def async_create_entry(self, title="", data=None):
        return {"type": "create_entry", "title": title, "data": data}

    def async_abort(self, reason=""):
        return {"type": "abort", "reason": reason}

    def async_show_menu(self, step_id=None, menu_options=None, description_placeholders=None):
        return {
            "type": "menu",
            "step_id": step_id,
            "menu_options": menu_options,
        }


sys.modules["homeassistant"].config_entries = sys.modules["homeassistant.config_entries"]
sys.modules["homeassistant.config_entries"].OptionsFlow = MockOptionsFlow
sys.modules["homeassistant.config_entries"].ConfigFlow = MockConfigFlow
sys.modules["homeassistant.components.bluetooth"].async_scanner_count = MagicMock(return_value=1)
sys.modules["homeassistant.components.bluetooth"].async_request_active_scan = AsyncMock()


class MockTextSelectorType(str, Enum):
    PASSWORD = "password"
    TEXT = "text"


class MockTextSelectorConfig:
    def __init__(self, type=MockTextSelectorType.TEXT, **kwargs):
        self.type = type


class MockTextSelector:
    def __init__(self, config=None):
        self.config = config


class MockVolKey:
    def __init__(self, key, default=None):
        self.schema = key
        self.default = default

    def __hash__(self):
        return hash(self.schema)

    def __eq__(self, other):
        if isinstance(other, MockVolKey):
            return self.schema == other.schema
        return self.schema == other


class MockVolSchema:
    def __init__(self, schema):
        self.schema = schema


sys.modules["homeassistant.helpers.selector"].TextSelector = MockTextSelector
sys.modules["homeassistant.helpers.selector"].TextSelectorConfig = MockTextSelectorConfig
sys.modules["homeassistant.helpers.selector"].TextSelectorType = MockTextSelectorType
sys.modules["voluptuous"].Schema = MockVolSchema
sys.modules["voluptuous"].Required = lambda k, default=None: MockVolKey(k, default)
sys.modules["voluptuous"].Optional = lambda k, default=None: MockVolKey(k, default)
