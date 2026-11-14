"""Lock entity for Sesame 5 BLE integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODEL_ID, LOCK_MODELS, TOUCH_MODELS
from .coordinator import Sesame5Coordinator
from .helpers import get_device_info

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    Sesame5ConfigEntry = ConfigEntry[Sesame5Coordinator]
else:
    Sesame5ConfigEntry = Any

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Sesame5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sesame 5 lock platform."""
    coordinator: Sesame5Coordinator = entry.runtime_data
    model_id = entry.data.get(CONF_MODEL_ID)
    if model_id is not None and model_id not in LOCK_MODELS:
        LOGGER.info(
            "[%s] Device (model %s) is not a door lock (e.g. Touch/Keypad), skipping lock entity",
            entry.title,
            model_id,
        )
        return
    if coordinator.device.is_keypad:
        LOGGER.info(
            "[%s] Device is detected as a keypad/touch device, skipping lock entity",
            entry.title,
        )
        return

    async_add_entities([Sesame5BleLock(coordinator, entry)])


class Sesame5BleLock(CoordinatorEntity[Sesame5Coordinator], LockEntity):
    """Representation of a Sesame 5 smart lock."""

    _attr_has_entity_name = True
    _attr_name = None  # Primary device entity inherits device name
    _attr_supported_features = LockEntityFeature.OPEN

    def __init__(
        self,
        coordinator: Sesame5Coordinator,
        entry: Sesame5ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_lock"
        self._attr_device_info = get_device_info(coordinator, entry)

    @property
    def is_locked(self) -> bool | None:
        data = self.coordinator.data
        if not data or not data.mech_status:
            return None
        return data.mech_status.is_locked()

    @property
    def is_locking(self) -> bool:
        data = self.coordinator.data
        if not data or not data.mech_status or not data.mech_settings:
            return False
        return (
            data.mech_status.target_position == data.mech_settings.lock_position
            and not data.mech_status.is_in_lock_range
        )

    @property
    def is_unlocking(self) -> bool:
        data = self.coordinator.data
        if not data or not data.mech_status or not data.mech_settings:
            return False
        return (
            data.mech_status.target_position == data.mech_settings.unlock_position
            and not data.mech_status.is_in_unlock_range
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs: dict[str, Any] = {
            "connection_mode": self.coordinator.connection_mode,
            "read_only_mode": self.coordinator.read_only,
        }
        data = self.coordinator.data
        if data and data.history:
            hist = data.history
            attrs["last_operation_method"] = hist.description_zh
            attrs["last_operation_source"] = hist.source
            attrs["last_operation_action"] = hist.action
            attrs["last_operation_time"] = hist.iso_timestamp
            if hist.tag_name:
                attrs["last_operation_tag"] = hist.tag_name
        return attrs

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the door."""
        await self.coordinator.lock()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the door."""
        await self.coordinator.unlock()

    async def async_open(self, **kwargs: Any) -> None:
        """Open / unlatch the door (triggers unlock in Sesame)."""
        await self.coordinator.unlock()
