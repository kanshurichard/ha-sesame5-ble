"""Sensor entities for Sesame 5 BLE integration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import DEGREE, PERCENTAGE, EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODEL_ID, LOCK_MODELS, TOUCH_MODELS
from .coordinator import Sesame5Coordinator
from .helpers import get_device_info

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    Sesame5ConfigEntry = ConfigEntry[Sesame5Coordinator]
else:
    Sesame5ConfigEntry = Any


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Sesame5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    model_id = entry.data.get(CONF_MODEL_ID)
    is_keypad = coordinator.device.is_keypad or (model_id is not None and model_id in TOUCH_MODELS)

    entities: list[SensorEntity] = [
        Sesame5BatterySensor(coordinator, entry),
        Sesame5VoltageSensor(coordinator, entry),
    ]

    if not is_keypad:
        entities.extend(
            [
                Sesame5PositionSensor(coordinator, entry),
                Sesame5LastOperationSensor(coordinator, entry),
                Sesame5LastOperationTimeSensor(coordinator, entry),
                Sesame5LastUnlockOperationSensor(coordinator, entry),
                Sesame5LastUnlockTimeSensor(coordinator, entry),
                Sesame5LastLockOperationSensor(coordinator, entry),
                Sesame5LastLockTimeSensor(coordinator, entry),
            ]
        )
    else:
        entities.extend(
            [
                SesameTouchPasswordCountSensor(coordinator, entry),
                SesameTouchFingerprintCountSensor(coordinator, entry),
                SesameTouchCardCountSensor(coordinator, entry),
            ]
        )

    async_add_entities(entities)


class Sesame5BatterySensor(CoordinatorEntity[Sesame5Coordinator], SensorEntity):
    """Battery percentage sensor for Sesame 5."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_battery"
        self._attr_device_info = get_device_info(coordinator, entry)

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if not data or not data.mech_status:
            return None
        return data.mech_status.battery_percentage


class Sesame5VoltageSensor(CoordinatorEntity[Sesame5Coordinator], SensorEntity):
    """Battery voltage sensor for Sesame 5."""

    _attr_has_entity_name = True
    _attr_translation_key = "voltage"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_voltage"
        self._attr_device_info = get_device_info(coordinator, entry)

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if not data or not data.mech_status:
            return None
        return data.mech_status.battery_voltage


class Sesame5PositionSensor(CoordinatorEntity[Sesame5Coordinator], SensorEntity):
    """Thumb turn position angle sensor for Sesame 5."""

    _attr_has_entity_name = True
    _attr_translation_key = "angle"
    _attr_native_unit_of_measurement = DEGREE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_angle"
        self._attr_device_info = get_device_info(coordinator, entry)

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if not data or not data.mech_status:
            return None
        return data.mech_status.position


class Sesame5LastOperationSensor(CoordinatorEntity[Sesame5Coordinator], RestoreEntity, SensorEntity):
    """Sensor displaying the last lock/unlock operation method (e.g. inside, fingerprint, auto-lock)."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_operation"
    _attr_icon = "mdi:lock-open-check"

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_last_operation"
        self._attr_device_info = get_device_info(coordinator, entry)
        self._restored_value: str | None = None
        self._restored_attrs: dict[str, Any] = {}

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if data and data.history:
            return data.history.description_zh
        return self._restored_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data and data.history:
            hist = data.history
            return {
                "source": hist.source,
                "action": hist.action,
                "tag": hist.tag_name,
                "accessory_type": hist.history_tag_type.name if hist.history_tag_type else None,
                "record_id": hist.record_id,
                "timestamp": hist.iso_timestamp,
            }
        return self._restored_attrs

    async def async_added_to_hass(self) -> None:
        """Restore previous state after Home Assistant restart."""
        await super().async_added_to_hass()
        if not (self.coordinator.data and self.coordinator.data.history):
            last_state = await self.async_get_last_state()
            if last_state and last_state.state not in (None, "unknown", "unavailable"):
                self._restored_value = last_state.state
                self._restored_attrs = dict(last_state.attributes)


class Sesame5LastOperationTimeSensor(CoordinatorEntity[Sesame5Coordinator], RestoreEntity, SensorEntity):
    """Sensor displaying the timestamp of the last lock/unlock operation."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_operation_time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_last_operation_time"
        self._attr_device_info = get_device_info(coordinator, entry)
        self._restored_value: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data
        if data and data.history and data.history.timestamp > 0:
            return datetime.fromtimestamp(data.history.timestamp, tz=timezone.utc)
        return self._restored_value

    async def async_added_to_hass(self) -> None:
        """Restore previous timestamp after Home Assistant restart."""
        await super().async_added_to_hass()
        if not (self.coordinator.data and self.coordinator.data.history):
            last_state = await self.async_get_last_state()
            if last_state and last_state.state not in (None, "unknown", "unavailable"):
                try:
                    self._restored_value = datetime.fromisoformat(last_state.state.replace("Z", "+00:00"))
                except Exception:
                    pass


class Sesame5LastUnlockOperationSensor(CoordinatorEntity[Sesame5Coordinator], RestoreEntity, SensorEntity):
    """Sensor displaying the last unlock operation method (e.g. fingerprint, passcode, manual)."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_unlock_operation"
    _attr_icon = "mdi:lock-open"

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_last_unlock_operation"
        self._attr_device_info = get_device_info(coordinator, entry)
        self._restored_value: str | None = None
        self._restored_attrs: dict[str, Any] = {}

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if data and data.last_unlock_history:
            return data.last_unlock_history.description_zh
        return self._restored_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data and data.last_unlock_history:
            hist = data.last_unlock_history
            return {
                "source": hist.source,
                "action": hist.action,
                "tag": hist.tag_name,
                "accessory_type": hist.history_tag_type.name if hist.history_tag_type else None,
                "record_id": hist.record_id,
                "timestamp": hist.iso_timestamp,
            }
        return self._restored_attrs

    async def async_added_to_hass(self) -> None:
        """Restore previous state after Home Assistant restart."""
        await super().async_added_to_hass()
        if not (self.coordinator.data and self.coordinator.data.last_unlock_history):
            last_state = await self.async_get_last_state()
            if last_state and last_state.state not in (None, "unknown", "unavailable"):
                self._restored_value = last_state.state
                self._restored_attrs = dict(last_state.attributes)


class Sesame5LastUnlockTimeSensor(CoordinatorEntity[Sesame5Coordinator], RestoreEntity, SensorEntity):
    """Sensor displaying the timestamp of the last unlock operation."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_unlock_time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_last_unlock_time"
        self._attr_device_info = get_device_info(coordinator, entry)
        self._restored_value: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data
        if data and data.last_unlock_history and data.last_unlock_history.timestamp > 0:
            return datetime.fromtimestamp(data.last_unlock_history.timestamp, tz=timezone.utc)
        return self._restored_value

    async def async_added_to_hass(self) -> None:
        """Restore previous timestamp after Home Assistant restart."""
        await super().async_added_to_hass()
        if not (self.coordinator.data and self.coordinator.data.last_unlock_history):
            last_state = await self.async_get_last_state()
            if last_state and last_state.state not in (None, "unknown", "unavailable"):
                try:
                    self._restored_value = datetime.fromisoformat(last_state.state.replace("Z", "+00:00"))
                except Exception:
                    pass


class Sesame5LastLockOperationSensor(CoordinatorEntity[Sesame5Coordinator], RestoreEntity, SensorEntity):
    """Sensor displaying the last lock operation method (e.g. autolock, manual lock, door-close auto-lock)."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_lock_operation"
    _attr_icon = "mdi:lock"

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_last_lock_operation"
        self._attr_device_info = get_device_info(coordinator, entry)
        self._restored_value: str | None = None
        self._restored_attrs: dict[str, Any] = {}

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if data and data.last_lock_history:
            return data.last_lock_history.description_zh
        return self._restored_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data and data.last_lock_history:
            hist = data.last_lock_history
            return {
                "source": hist.source,
                "action": hist.action,
                "tag": hist.tag_name,
                "accessory_type": hist.history_tag_type.name if hist.history_tag_type else None,
                "record_id": hist.record_id,
                "timestamp": hist.iso_timestamp,
            }
        return self._restored_attrs

    async def async_added_to_hass(self) -> None:
        """Restore previous state after Home Assistant restart."""
        await super().async_added_to_hass()
        if not (self.coordinator.data and self.coordinator.data.last_lock_history):
            last_state = await self.async_get_last_state()
            if last_state and last_state.state not in (None, "unknown", "unavailable"):
                self._restored_value = last_state.state
                self._restored_attrs = dict(last_state.attributes)


class Sesame5LastLockTimeSensor(CoordinatorEntity[Sesame5Coordinator], RestoreEntity, SensorEntity):
    """Sensor displaying the timestamp of the last lock operation."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_lock_time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_last_lock_time"
        self._attr_device_info = get_device_info(coordinator, entry)
        self._restored_value: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data
        if data and data.last_lock_history and data.last_lock_history.timestamp > 0:
            return datetime.fromtimestamp(data.last_lock_history.timestamp, tz=timezone.utc)
        return self._restored_value

    async def async_added_to_hass(self) -> None:
        """Restore previous timestamp after Home Assistant restart."""
        await super().async_added_to_hass()
        if not (self.coordinator.data and self.coordinator.data.last_lock_history):
            last_state = await self.async_get_last_state()
            if last_state and last_state.state not in (None, "unknown", "unavailable"):
                try:
                    self._restored_value = datetime.fromisoformat(last_state.state.replace("Z", "+00:00"))
                except Exception:
                    pass


class SesameTouchPasswordCountSensor(CoordinatorEntity[Sesame5Coordinator], SensorEntity):
    """Number of registered passwords on Sesame Touch."""

    _attr_has_entity_name = True
    _attr_translation_key = "password_count"
    _attr_icon = "mdi:numeric"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_password_count"
        self._attr_device_info = get_device_info(coordinator, entry)

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.passcode_count


class SesameTouchFingerprintCountSensor(CoordinatorEntity[Sesame5Coordinator], SensorEntity):
    """Number of registered fingerprints on Sesame Touch."""

    _attr_has_entity_name = True
    _attr_translation_key = "fingerprint_count"
    _attr_icon = "mdi:fingerprint"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_fingerprint_count"
        self._attr_device_info = get_device_info(coordinator, entry)

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.fingerprint_count


class SesameTouchCardCountSensor(CoordinatorEntity[Sesame5Coordinator], SensorEntity):
    """Number of registered cards on Sesame Touch."""

    _attr_has_entity_name = True
    _attr_translation_key = "card_count"
    _attr_icon = "mdi:smart-card"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_card_count"
        self._attr_device_info = get_device_info(coordinator, entry)

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.card_count
