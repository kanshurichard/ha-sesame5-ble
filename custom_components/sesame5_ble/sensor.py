"""Sensor entities for Sesame 5 BLE integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import DEGREE, PERCENTAGE, EntityCategory, UnitOfElectricPotential
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
            Sesame5BatterySensor(coordinator, entry),
            Sesame5VoltageSensor(coordinator, entry),
            Sesame5PositionSensor(coordinator, entry),
        ]
    )


class Sesame5BatterySensor(CoordinatorEntity[Sesame5Coordinator], SensorEntity):
    """Battery percentage sensor for Sesame 5."""

    _attr_has_entity_name = True
    _attr_name = "Battery"
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
    _attr_name = "Battery Voltage"
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
    _attr_name = "Angle"
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
