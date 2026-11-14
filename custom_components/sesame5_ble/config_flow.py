"""Config flow for Sesame 5 BLE integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    COMPANY_ID,
    CONF_DEVICE_ID,
    CONF_HISTORY_TAG,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_READ_ONLY,
    CONF_REFRESH_INTERVAL,
    CONF_SECRET_KEY,
    DEFAULT_HISTORY_TAG,
    DEFAULT_READ_ONLY,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
    PRODUCT_NAMES,
    SERVICE_UUID,
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
                return await self.async_step_auth()

            errors["base"] = "device_not_found"

        scanned = _scan_sesame5_devices(self.hass)
        self._discovered_devices = {d[CONF_ADDRESS]: d for d in scanned}

        options = [
            {"value": d[CONF_ADDRESS], "label": f"{d['name']} ({d['rssi']} dBm)"}
            for d in scanned
        ]
        options.append({"value": "manual", "label": "Enter Bluetooth MAC manually..."})

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual address input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._selected_address = user_input[CONF_ADDRESS].strip()
            self._selected_model = user_input.get(CONF_MODEL, "Sesame 5")
            self._selected_device_id = self._selected_address
            return await self.async_step_auth()

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): str,
                vol.Optional(CONF_MODEL, default="Sesame 5"): str,
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
                )

                try:
                    LOGGER.debug("[%s] Verifying authentication credentials", address)
                    await device.authenticate()
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

                    return self.async_create_entry(
                        title=f"{self._selected_model} ({address[-5:].replace(':', '')})",
                        data={
                            CONF_ADDRESS: address,
                            CONF_DEVICE_ID: self._selected_device_id or address,
                            CONF_SECRET_KEY: secret_key_bytes.hex(),
                            CONF_MODEL: self._selected_model,
                            CONF_MODEL_ID: self._selected_model_id,
                            CONF_HISTORY_TAG: history_tag,
                            CONF_READ_ONLY: user_input.get(CONF_READ_ONLY, DEFAULT_READ_ONLY),
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_SECRET_KEY): str,
                vol.Optional(CONF_HISTORY_TAG, default=DEFAULT_HISTORY_TAG): str,
                vol.Optional(CONF_READ_ONLY, default=DEFAULT_READ_ONLY): bool,
            }
        )

        return self.async_show_form(
            step_id="auth",
            data_schema=schema,
            description_placeholders={"device_name": f"{self._selected_model} ({address})"},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return Sesame5OptionsFlowHandler(config_entry)


class Sesame5OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Sesame 5 BLE integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

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
                vol.Optional(CONF_REFRESH_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1440)
                ),
                vol.Optional(CONF_HISTORY_TAG, default=current_tag): str,
                vol.Optional(CONF_READ_ONLY, default=current_read_only): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
