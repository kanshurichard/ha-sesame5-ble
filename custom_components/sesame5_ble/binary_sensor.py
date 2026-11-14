"""Binary sensor entities for Sesame 5 BLE integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
    async_add_entities(
        [
            Sesame5BatteryCriticalBinarySensor(coordinator, entry),
            Sesame5MovingBinarySensor(coordinator, entry),
        ]
    )


class Sesame5BatteryCriticalBinarySensor(CoordinatorEntity[Sesame5Coordinator], BinarySensorEntity):
    """Binary sensor alerting when lock battery is critically low."""

    _attr_has_entity_name = True
    _attr_name = "Battery Low"
    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_battery_critical"
        self._attr_device_info = get_device_info(coordinator, entry)

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data or not data.mech_status:
            return None
        return data.mech_status.is_battery_critical


class Sesame5MovingBinarySensor(CoordinatorEntity[Sesame5Coordinator], BinarySensorEntity):
    """Binary sensor indicating whether the lock motor is currently active."""

    _attr_has_entity_name = True
    _attr_name = "Motor Active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_moving"
        self._attr_device_info = get_device_info(coordinator, entry)

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data or not data.mech_status:
            return None
        return not data.mech_status.is_stop
