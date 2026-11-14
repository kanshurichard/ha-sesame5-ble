"""The Sesame 5 BLE integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_HISTORY_TAG, CONF_SECRET_KEY, DEFAULT_HISTORY_TAG
from .coordinator import Sesame5Coordinator
from .device import Sesame5Device

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    Sesame5ConfigEntry = ConfigEntry[Sesame5Coordinator]
else:
    Sesame5ConfigEntry = Any

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: Sesame5ConfigEntry) -> bool:
    """Set up Sesame 5 BLE from a config entry."""
    address = entry.data[CONF_ADDRESS]
    secret_key_hex = entry.data[CONF_SECRET_KEY]
    history_tag = entry.options.get(
        CONF_HISTORY_TAG,
        entry.data.get(CONF_HISTORY_TAG, DEFAULT_HISTORY_TAG),
    )

    try:
        secret_key_bytes = bytes.fromhex(secret_key_hex)
    except ValueError as err:
        LOGGER.error("[%s] Invalid hex secret key in configuration", address)
        return False

    device = Sesame5Device(
        address=address,
        secret_key=secret_key_bytes,
        hass=hass,
        history_tag=history_tag,
    )

    coordinator = Sesame5Coordinator(hass, entry, device)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        LOGGER.warning("[%s] Initial connection to Sesame 5 failed: %s (will retry)", address, err)
        await coordinator.shutdown()
        raise ConfigEntryNotReady from err

    coordinator.start_periodic_refresh()

    async def _update_options(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        coordinator.restart_periodic_refresh()

    entry.async_on_unload(entry.add_update_listener(_update_options))
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Sesame5ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.runtime_data:
        await entry.runtime_data.shutdown()
    return unload_ok
