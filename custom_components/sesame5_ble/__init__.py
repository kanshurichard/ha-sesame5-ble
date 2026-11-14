"""The Sesame 5 BLE integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

try:
    from homeassistant.core import SupportsResponse

    SUPPORTS_RESPONSE_OPTIONAL = SupportsResponse.OPTIONAL
except ImportError:
    SUPPORTS_RESPONSE_OPTIONAL = None

from .const import (
    ATTR_DURATION,
    ATTR_NAME,
    ATTR_ONE_TIME,
    ATTR_PASSCODE,
    CONF_HISTORY_TAG,
    CONF_MODEL_ID,
    CONF_SECRET_KEY,
    DEFAULT_HISTORY_TAG,
    DOMAIN,
    SERVICE_ADD_PASSCODE,
    SERVICE_DELETE_PASSCODE,
    SERVICE_GET_PASSCODES,
    TOUCH_MODELS,
)
from .coordinator import Sesame5Coordinator
from .device import Sesame5Device

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    Sesame5ConfigEntry = ConfigEntry[Sesame5Coordinator]
else:
    Sesame5ConfigEntry = Any

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


def _get_entry_platforms(entry: ConfigEntry) -> list[Platform]:
    """Return platforms to setup for a given config entry."""
    model_id = entry.data.get(CONF_MODEL_ID)
    if model_id is not None and model_id in TOUCH_MODELS:
        return [Platform.SENSOR, Platform.BINARY_SENSOR]
    return PLATFORMS


def _get_coordinators_from_call(hass: HomeAssistant, call: ServiceCall) -> list[Sesame5Coordinator]:
    """Extract Sesame5Coordinator instances from service call targets."""
    target_coordinators: list[Sesame5Coordinator] = []
    device_id = call.data.get("device_id")
    address = call.data.get("address")

    if address:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if hasattr(entry, "runtime_data") and entry.runtime_data:
                coord = entry.runtime_data
                if coord.address.lower() == address.lower():
                    target_coordinators.append(coord)
        return target_coordinators

    if device_id:
        dev_reg = dr.async_get(hass)
        device_entry = dev_reg.async_get(device_id)
        if device_entry:
            for config_entry_id in device_entry.config_entries:
                entry = hass.config_entries.async_get_entry(config_entry_id)
                if entry and entry.domain == DOMAIN and hasattr(entry, "runtime_data") and entry.runtime_data:
                    target_coordinators.append(entry.runtime_data)
        return target_coordinators

    # Fallback: if single keypad exists, use it
    keypad_coords = []
    all_coords = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if hasattr(entry, "runtime_data") and entry.runtime_data:
            coord = entry.runtime_data
            all_coords.append(coord)
            if coord.device.is_keypad:
                keypad_coords.append(coord)

    if len(keypad_coords) == 1:
        return keypad_coords
    if len(all_coords) == 1:
        return all_coords

    return target_coordinators


async def async_setup_entry(hass: HomeAssistant, entry: Sesame5ConfigEntry) -> bool:
    """Set up Sesame 5 BLE from a config entry."""
    address = entry.data[CONF_ADDRESS]
    secret_key_hex = entry.data[CONF_SECRET_KEY]
    history_tag = entry.options.get(
        CONF_HISTORY_TAG,
        entry.data.get(CONF_HISTORY_TAG, DEFAULT_HISTORY_TAG),
    )
    model_id = entry.data.get(CONF_MODEL_ID)

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
        model_id=model_id,
    )

    coordinator = Sesame5Coordinator(hass, entry, device)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        LOGGER.warning("[%s] Initial connection to Sesame device failed: %s (will retry)", address, err)
        await coordinator.shutdown()
        raise ConfigEntryNotReady from err

    coordinator.start_periodic_refresh()

    async def _update_options(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        coordinator.restart_periodic_refresh()

    entry.async_on_unload(entry.add_update_listener(_update_options))
    entry.runtime_data = coordinator

    platforms = _get_entry_platforms(entry)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    # Register keypad services once
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_PASSCODE):

        async def _handle_add_passcode(call: ServiceCall) -> None:
            coordinators = _get_coordinators_from_call(hass, call)
            if not coordinators:
                raise HomeAssistantError("未找到目标 Sesame 键盘设备，请在服务调用中指定 device_id 或 address。")

            passcode = str(call.data[ATTR_PASSCODE]).strip()
            name = str(call.data.get(ATTR_NAME, "HA Temp")).strip()
            duration = call.data.get(ATTR_DURATION)
            one_time = bool(call.data.get(ATTR_ONE_TIME, False))

            for coord in coordinators:
                await coord.async_add_passcode(
                    passcode=passcode,
                    name=name,
                    duration=duration,
                    one_time=one_time,
                )

        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_PASSCODE,
            _handle_add_passcode,
            schema=vol.Schema(
                {
                    vol.Optional("device_id"): cv.string,
                    vol.Optional("address"): cv.string,
                    vol.Required(ATTR_PASSCODE): cv.string,
                    vol.Optional(ATTR_NAME, default="HA Temp"): cv.string,
                    vol.Optional(ATTR_DURATION): vol.Coerce(int),
                    vol.Optional(ATTR_ONE_TIME, default=False): cv.boolean,
                }
            ),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_PASSCODE):

        async def _handle_delete_passcode(call: ServiceCall) -> None:
            coordinators = _get_coordinators_from_call(hass, call)
            if not coordinators:
                raise HomeAssistantError("未找到目标 Sesame 键盘设备，请在服务调用中指定 device_id 或 address。")

            passcode = str(call.data[ATTR_PASSCODE]).strip()
            for coord in coordinators:
                await coord.async_delete_passcode(passcode)

        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_PASSCODE,
            _handle_delete_passcode,
            schema=vol.Schema(
                {
                    vol.Optional("device_id"): cv.string,
                    vol.Optional("address"): cv.string,
                    vol.Required(ATTR_PASSCODE): cv.string,
                }
            ),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_PASSCODES):

        async def _handle_get_passcodes(call: ServiceCall) -> ServiceResponse:
            coordinators = _get_coordinators_from_call(hass, call)
            if not coordinators:
                raise HomeAssistantError("未找到目标 Sesame 键盘设备，请在服务调用中指定 device_id 或 address。")

            results: dict[str, Any] = {}
            for coord in coordinators:
                passcodes = await coord.async_get_passcodes()
                results[coord.address] = passcodes
            return {"devices": results}

        kwargs: dict[str, Any] = {
            "schema": vol.Schema(
                {
                    vol.Optional("device_id"): cv.string,
                    vol.Optional("address"): cv.string,
                }
            )
        }
        if SUPPORTS_RESPONSE_OPTIONAL is not None:
            kwargs["supports_response"] = SUPPORTS_RESPONSE_OPTIONAL

        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_PASSCODES,
            _handle_get_passcodes,
            **kwargs,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: Sesame5ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = _get_entry_platforms(entry)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok and entry.runtime_data:
        await entry.runtime_data.shutdown()
    return unload_ok
