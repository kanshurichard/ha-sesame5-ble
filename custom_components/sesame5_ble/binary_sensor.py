"""Binary sensor entities for Sesame 5 BLE integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODEL_ID, DOMAIN, TOUCH_MODELS
from .coordinator import Sesame5Coordinator
from .helpers import get_device_info

LOGGER = logging.getLogger(__name__)

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

    entities: list[BinarySensorEntity] = [
        Sesame5BatteryCriticalBinarySensor(coordinator, entry),
    ]

    if not is_keypad:
        entities.append(Sesame5MovingBinarySensor(coordinator, entry))
        entities.append(Sesame5DoorBinarySensor(coordinator, entry))

    async_add_entities(entities)


class Sesame5DoorBinarySensor(CoordinatorEntity[Sesame5Coordinator], RestoreEntity, BinarySensorEntity):
    """Binary sensor indicating whether the door is open or closed (via paired Open Sensor)."""

    _attr_has_entity_name = True
    _attr_translation_key = "door"
    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: Sesame5Coordinator, entry: Sesame5ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_door"
        self._attr_device_info = get_device_info(coordinator, entry)
        # If no door sensor state has been detected yet, hide by default from UI
        has_door_sensor = bool(coordinator.data and coordinator.data.door_open is not None)
        self._attr_entity_registry_visible_default = has_door_sensor

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.door_open

    async def async_added_to_hass(self) -> None:
        """Restore previous door state after Home Assistant restart and synchronize visibility."""
        await super().async_added_to_hass()
        if self.coordinator.data and self.coordinator.data.door_open is None:
            last_state = await self.async_get_last_state()
            if last_state and last_state.state in ("on", "off"):
                self.coordinator.device.set_door_open(last_state.state == "on")
                self.coordinator.async_set_updated_data(self.coordinator._current_state)

        self._sync_visibility()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator and synchronize visibility when door sensor reports."""
        self._sync_visibility()
        super()._handle_coordinator_update()

    def _sync_visibility(self) -> None:
        """Synchronize door sensor visibility: hide by default when not detected, unhide when detected."""
        if not self.hass:
            return

        ent_reg = er.async_get(self.hass)
        reg_entry = ent_reg.async_get(self.entity_id)
        if not reg_entry:
            return

        has_door_sensor = bool(self.coordinator.data and self.coordinator.data.door_open is not None)

        if has_door_sensor:
            # If Open Sensor is now detected and entity was hidden by integration, unhide it!
            if reg_entry.hidden_by == er.RegistryEntryHider.INTEGRATION:
                LOGGER.info(
                    "[%s] Open Sensor detected; unhiding door status sensor (%s)",
                    self.coordinator.address,
                    self.entity_id,
                )
                ent_reg.async_update_entity(self.entity_id, hidden_by=None)
        else:
            # No Open Sensor detected:
            # For existing/upgraded entries, ensure it is hidden by default if never initialized
            sub_options = reg_entry.options.get(DOMAIN, {}) if reg_entry.options else {}
            if not sub_options.get("visibility_initialized"):
                ent_reg.async_update_entity_options(
                    self.entity_id,
                    DOMAIN,
                    {**sub_options, "visibility_initialized": True},
                )
                if reg_entry.hidden_by is None:
                    LOGGER.info(
                        "[%s] No Open Sensor detected; hiding door status sensor by default (%s)",
                        self.coordinator.address,
                        self.entity_id,
                    )
                    ent_reg.async_update_entity(
                        self.entity_id,
                        hidden_by=er.RegistryEntryHider.INTEGRATION,
                    )


class Sesame5BatteryCriticalBinarySensor(CoordinatorEntity[Sesame5Coordinator], BinarySensorEntity):
    """Binary sensor alerting when lock battery is critically low."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery_critical"
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
    _attr_translation_key = "moving"
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
