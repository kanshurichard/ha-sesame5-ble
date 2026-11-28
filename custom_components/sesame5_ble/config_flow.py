# Copyright (c) 2026 kanshurichard
# Portions based on ha-sesame-ble (Copyright (c) 2026 ngoc-minh-do) and gomalock (Copyright (c) 2026 meronepy).
# Licensed under the MIT License. See LICENSE and NOTICE in the repository root for details.

"""Config flow for Sesame 5 BLE integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_request_active_scan,
    async_scanner_count,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    COMPANY_ID,
    CONF_CONNECTION_MODE,
    CONF_DEVICE_ID,
    CONF_HISTORY_TAG,
    CONF_LINKED_LOCK,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_READ_ONLY,
    CONF_REFRESH_INTERVAL,
    CONF_SECRET_KEY,
    CONNECTION_MODE_POWER_SAVING,
    CONNECTION_MODE_REALTIME,
    DEFAULT_CONNECTION_MODE,
    DEFAULT_HISTORY_TAG,
    DEFAULT_LINKED_LOCK,
    DEFAULT_READ_ONLY,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
    MANUAL_MODEL_OPTIONS,
    MODEL_NAME_TO_ID,
    PRODUCT_NAMES,
    ProductModel,
    SERVICE_UUID,
    TOUCH_MODELS,
)
from .device import Sesame5Device
from .helpers import Sesame5Advertisement, parse_secret_key_input

LOGGER = logging.getLogger(__name__)


def _scan_sesame5_devices(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Scan and return discovered Sesame 5 BLE devices."""
    devices: list[dict[str, Any]] = []
    discovered_ble = list(async_discovered_service_info(hass))

    for info in discovered_ble:
        has_service = SERVICE_UUID.lower() in [u.lower() for u in info.advertisement.service_uuids]
        has_company = COMPANY_ID in info.advertisement.manufacturer_data
        if not (has_service or has_company):
            continue

        adv = Sesame5Advertisement(info.device, info.advertisement.manufacturer_data)
        model_name = adv.model_name
        uuid_str = str(adv.device_uuid) if adv.device_uuid else ""

        devices.append(
            {
                CONF_ADDRESS: info.address,
                CONF_MODEL: model_name,
                CONF_MODEL_ID: adv.model_id,
                CONF_DEVICE_ID: uuid_str or info.address,
                "name": f"{model_name} ({info.address})",
                "rssi": info.rssi,
            }
        )

    # Sort strongest signal first
    devices.sort(key=lambda d: d.get("rssi", -100), reverse=True)
    return devices


def _is_keypad_model(model_id: int | None, model_name: str | None = None) -> bool:
    """Return True if model is a keypad/touch device."""
    if model_id is not None and model_id in TOUCH_MODELS:
        return True
    if model_name:
        name_lower = model_name.lower()
        if "touch" in name_lower or "keypad" in name_lower or "键盘" in name_lower:
            return True
    return False


def _is_entry_keypad(entry: config_entries.ConfigEntry) -> bool:
    """Check if config entry represents a keypad/touch device."""
    data = getattr(entry, "data", {})
    options = getattr(entry, "options", {})
    model_id = data.get(CONF_MODEL_ID) if isinstance(data, dict) else None
    model_name = data.get(CONF_MODEL, "") if isinstance(data, dict) else ""
    if _is_keypad_model(model_id, model_name):
        return True
    title = str(getattr(entry, "title", ""))
    if "touch" in title.lower() or "keypad" in title.lower() or "键盘" in title:
        return True
    if isinstance(data, dict) and CONF_LINKED_LOCK in data:
        return True
    if isinstance(options, dict) and CONF_LINKED_LOCK in options:
        return True
    if hasattr(entry, "runtime_data") and entry.runtime_data:
        device = getattr(entry.runtime_data, "device", None)
        if device and getattr(device, "is_keypad", False) is True:
            return True
    return False


def _get_configured_locks(hass: HomeAssistant, exclude_address: str | None = None) -> list[dict[str, str]]:
    """Return list of configured Sesame lock entries for keypad binding dropdown."""
    options = [
        {
            "value": DEFAULT_LINKED_LOCK,
            "label": "Auto",
        }
    ]
    for entry in hass.config_entries.async_entries(DOMAIN):
        addr = entry.data.get(CONF_ADDRESS)
        if not addr or (exclude_address and addr.upper() == exclude_address.upper()):
            continue
        if _is_entry_keypad(entry):
            continue
        options.append(
            {
                "value": addr,
                "label": f"{entry.title} ({addr})",
            }
        )
    return options


class Sesame5ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sesame 5 BLE."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_devices: dict[str, dict[str, Any]] = {}
        self._selected_address: str | None = None
        self._selected_model: str = "Sesame 5"
        self._selected_model_id: int | None = None
        self._selected_device_id: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle discovery by Bluetooth integration."""
        address = discovery_info.address
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()

        adv = Sesame5Advertisement(discovery_info.device, discovery_info.advertisement.manufacturer_data)
        self._selected_address = address
        self._selected_model = adv.model_name
        self._selected_model_id = adv.model_id
        self._selected_device_id = str(adv.device_uuid) if adv.device_uuid else address

        self.context["title_placeholders"] = {
            "name": f"{self._selected_model} ({address})",
        }
        return await self.async_step_auth()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle initial step: device discovery selection or manual input."""
        errors: dict[str, str] = {}

        if not async_scanner_count(self.hass, connectable=True):
            return self.async_abort(reason="bluetooth_not_available")

        if user_input is not None:
            address = user_input.get(CONF_ADDRESS)
            if address == "manual":
                return await self.async_step_manual()

            if address in self._discovered_devices:
                dev = self._discovered_devices[address]
                self._selected_address = address
                self._selected_model = dev[CONF_MODEL]
                self._selected_model_id = dev[CONF_MODEL_ID]
                self._selected_device_id = dev[CONF_DEVICE_ID]

                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()

                return await self.async_step_auth()

            errors["base"] = "device_not_found"

        configured_addresses = {
            uid.upper() for uid in self._async_current_ids(include_ignore=False) if uid
        } | {
            str(entry.data.get(CONF_ADDRESS, "")).upper()
            for entry in self._async_current_entries()
            if entry.data.get(CONF_ADDRESS)
        }

        scanned = _scan_sesame5_devices(self.hass)
        unconfigured = [
            d for d in scanned
            if d[CONF_ADDRESS].upper() not in configured_addresses
        ]

        if not unconfigured:
            # No new/unconfigured devices found via Bluetooth broadcast.
            # Ask user if they would like to enter MAC manually or retry.
            return await self.async_step_no_devices()

        self._discovered_devices = {d[CONF_ADDRESS]: d for d in unconfigured}

        options = [
            {"value": d[CONF_ADDRESS], "label": f"{d['name']} ({d['rssi']} dBm)"}
            for d in unconfigured
        ]
        options.append({"value": "manual", "label": "Enter Bluetooth MAC manually..."})

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        translation_key="device_selection",
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_no_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle no devices found step: ask user if they want to enter manually or rescan."""
        return self.async_show_menu(
            step_id="no_devices",
            menu_options=["manual", "retry"],
        )

    async def async_step_retry(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Rescan for Bluetooth devices."""
        await async_request_active_scan(self.hass)
        return await self.async_step_user()

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual address input."""
        errors: dict[str, str] = {}

        if not async_scanner_count(self.hass, connectable=True):
            return self.async_abort(reason="bluetooth_not_available")

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            self._selected_address = address
            self._selected_model = user_input.get(CONF_MODEL, "Sesame 5")
            self._selected_model_id = MODEL_NAME_TO_ID.get(
                self._selected_model, ProductModel.SESAME_5.value
            )
            self._selected_device_id = address
            return await self.async_step_auth()

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): str,
                vol.Required(CONF_MODEL, default="Sesame 5"): SelectSelector(
                    SelectSelectorConfig(
                        options=MANUAL_MODEL_OPTIONS,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Prompt for Secret Key / QR code and verify connection."""
        errors: dict[str, str] = {}
        address = self._selected_address
        assert address is not None

        is_keypad = _is_keypad_model(self._selected_model_id, self._selected_model)

        if user_input is not None:
            raw_key_input = user_input[CONF_SECRET_KEY]
            history_tag = user_input.get(CONF_HISTORY_TAG, DEFAULT_HISTORY_TAG).strip() or DEFAULT_HISTORY_TAG

            try:
                secret_key_bytes, device_uuid, model_id = parse_secret_key_input(raw_key_input)
                if device_uuid and not self._selected_device_id:
                    self._selected_device_id = device_uuid
                if model_id and model_id in PRODUCT_NAMES:
                    self._selected_model = PRODUCT_NAMES[model_id]
                    self._selected_model_id = model_id
                    is_keypad = _is_keypad_model(model_id, self._selected_model)
            except ValueError as exc:
                LOGGER.warning("Invalid key input: %s", exc)
                errors["base"] = "invalid_key_format"
                secret_key_bytes = None

            if secret_key_bytes:
                # Test connection and login
                device = Sesame5Device(
                    address=address,
                    secret_key=secret_key_bytes,
                    hass=self.hass,
                    history_tag=history_tag,
                    model_id=self._selected_model_id,
                )

                try:
                    LOGGER.debug("[%s] Verifying authentication credentials", address)
                    await device.authenticate()
                    if device.is_keypad:
                        is_keypad = True
                except TimeoutError:
                    errors["base"] = "cannot_connect"
                except Exception as exc:
                    LOGGER.exception("[%s] Authentication verification failed", address)
                    errors["base"] = "invalid_auth"
                finally:
                    await device.disconnect()

                if not errors:
                    await self.async_set_unique_id(address)
                    self._abort_if_unique_id_configured()

                    entry_data = {
                        CONF_ADDRESS: address,
                        CONF_DEVICE_ID: self._selected_device_id or address,
                        CONF_SECRET_KEY: secret_key_bytes.hex(),
                        CONF_MODEL: self._selected_model,
                        CONF_MODEL_ID: self._selected_model_id,
                        CONF_HISTORY_TAG: history_tag,
                        CONF_READ_ONLY: user_input.get(CONF_READ_ONLY, DEFAULT_READ_ONLY),
                    }
                    if is_keypad:
                        entry_data[CONF_CONNECTION_MODE] = CONNECTION_MODE_POWER_SAVING
                        entry_data[CONF_LINKED_LOCK] = user_input.get(CONF_LINKED_LOCK, DEFAULT_LINKED_LOCK)
                    else:
                        entry_data[CONF_CONNECTION_MODE] = user_input.get(CONF_CONNECTION_MODE, DEFAULT_CONNECTION_MODE)

                    return self.async_create_entry(
                        title=f"{self._selected_model} ({address[-5:].replace(':', '')})",
                        data=entry_data,
                    )

        if is_keypad:
            lock_options = _get_configured_locks(self.hass, address)
            schema = vol.Schema(
                {
                    vol.Required(CONF_SECRET_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(
                        CONF_LINKED_LOCK,
                        default=DEFAULT_LINKED_LOCK,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=lock_options,
                            translation_key="linked_lock",
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_HISTORY_TAG, default=DEFAULT_HISTORY_TAG): str,
                    vol.Optional(CONF_READ_ONLY, default=DEFAULT_READ_ONLY): bool,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_SECRET_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(
                        CONF_CONNECTION_MODE,
                        default=DEFAULT_CONNECTION_MODE,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                CONNECTION_MODE_REALTIME,
                                CONNECTION_MODE_POWER_SAVING,
                            ],
                            translation_key="connection_mode",
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_HISTORY_TAG, default=DEFAULT_HISTORY_TAG): str,
                    vol.Optional(CONF_READ_ONLY, default=DEFAULT_READ_ONLY): bool,
                }
            )

        step_id = "auth_keypad" if is_keypad else "auth"
        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            description_placeholders={"device_name": f"{self._selected_model} ({address})"},
            errors=errors,
        )

    async def async_step_auth_keypad(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle auth step specifically for keypad devices."""
        return await self.async_step_auth(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return Sesame5OptionsFlowHandler()


class Sesame5OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Sesame 5 BLE integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage integration options."""
        if _is_entry_keypad(self.config_entry):
            return await self.async_step_keypad(user_input)

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_mode = self.config_entry.options.get(
            CONF_CONNECTION_MODE,
            self.config_entry.data.get(CONF_CONNECTION_MODE, DEFAULT_CONNECTION_MODE),
        )
        current_interval = self.config_entry.options.get(
            CONF_REFRESH_INTERVAL,
            self.config_entry.data.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL),
        )
        current_tag = self.config_entry.options.get(
            CONF_HISTORY_TAG,
            self.config_entry.data.get(CONF_HISTORY_TAG, DEFAULT_HISTORY_TAG),
        )
        current_read_only = self.config_entry.options.get(
            CONF_READ_ONLY,
            self.config_entry.data.get(CONF_READ_ONLY, DEFAULT_READ_ONLY),
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CONNECTION_MODE,
                    default=current_mode,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            CONNECTION_MODE_REALTIME,
                            CONNECTION_MODE_POWER_SAVING,
                        ],
                        translation_key="connection_mode",
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_REFRESH_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1440)
                ),
                vol.Optional(CONF_HISTORY_TAG, default=current_tag): str,
                vol.Optional(CONF_READ_ONLY, default=current_read_only): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_keypad(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage keypad options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_read_only = self.config_entry.options.get(
            CONF_READ_ONLY,
            self.config_entry.data.get(CONF_READ_ONLY, DEFAULT_READ_ONLY),
        )
        current_linked_lock = self.config_entry.options.get(
            CONF_LINKED_LOCK,
            self.config_entry.data.get(CONF_LINKED_LOCK, DEFAULT_LINKED_LOCK),
        )
        lock_options = _get_configured_locks(
            self.hass,
            exclude_address=self.config_entry.data.get(CONF_ADDRESS),
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LINKED_LOCK,
                    default=current_linked_lock,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=lock_options,
                        translation_key="linked_lock",
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_READ_ONLY, default=current_read_only): bool,
            }
        )
        return self.async_show_form(step_id="keypad", data_schema=schema)
