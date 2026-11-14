"""DataUpdateCoordinator for Sesame 5 BLE integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HISTORY_TAG,
    CONF_READ_ONLY,
    CONF_REFRESH_INTERVAL,
    DEFAULT_HISTORY_TAG,
    DEFAULT_READ_ONLY,
    DEFAULT_REFRESH_INTERVAL,
)
from .device import Sesame5Device
from .helpers import Sesame5HistoryRecord, Sesame5MechSetting, Sesame5MechStatus

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

LOGGER = logging.getLogger(__name__)


@dataclass
class Sesame5State:
    """Snapshot of Sesame 5 mechanical status and configuration."""

    mech_status: Sesame5MechStatus | None
    mech_settings: Sesame5MechSetting | None
    history: Sesame5HistoryRecord | None = None


class Sesame5Coordinator(DataUpdateCoordinator[Sesame5State]):
    """Coordinates BLE connection lifecycle, concurrency, and Home Assistant state synchronization."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: Sesame5Device,
    ) -> None:
        self._device = device
        self._connection_lock = asyncio.Lock()

        super().__init__(
            hass,
            LOGGER,
            name=f"Sesame 5 BLE ({device.address})",
            config_entry=entry,
            update_interval=None,
        )

        self._device.add_update_callback(self._on_device_update)

    @property
    def address(self) -> str:
        return self._device.address

    @property
    def device(self) -> Sesame5Device:
        return self._device

    @property
    def history_tag(self) -> str:
        if self.config_entry:
            return self.config_entry.options.get(
                CONF_HISTORY_TAG,
                self.config_entry.data.get(CONF_HISTORY_TAG, DEFAULT_HISTORY_TAG),
            )
        return DEFAULT_HISTORY_TAG

    @property
    def read_only(self) -> bool:
        if self.config_entry:
            return bool(
                self.config_entry.options.get(
                    CONF_READ_ONLY,
                    self.config_entry.data.get(CONF_READ_ONLY, DEFAULT_READ_ONLY),
                )
            )
        return DEFAULT_READ_ONLY

    @property
    def _current_state(self) -> Sesame5State:
        return Sesame5State(
            mech_status=self._device.mech_status,
            mech_settings=self._device.mech_settings,
            history=self._device.history,
        )

    async def _async_update_data(self) -> Sesame5State:
        """Fetch latest state from device via BLE."""
        try:
            await self._ensure_connected()
        except Exception as err:
            raise UpdateFailed(f"Unable to refresh Sesame 5 state: {err}") from err
        return self._current_state

    def _on_device_update(self) -> None:
        """Callback from device when notification is processed."""
        self.async_set_updated_data(self._current_state)

    async def _ensure_connected(self) -> None:
        """Ensure active and authenticated BLE connection to lock."""
        async with self._connection_lock:
            if self._device.is_ready:
                return

            LOGGER.debug("[%s] Coordinator establishing on-demand connection", self.address)
            await self._device.authenticate()

    async def lock(self, tag: str | None = None) -> None:
        """Lock the door."""
        if self.read_only:
            raise HomeAssistantError("Sesame 5 当前处于只读模式，已禁止远程施锁操作。如需操作，请在集成选项中关闭只读模式。")
        await self._ensure_connected()
        await self._device.lock(tag or self.history_tag)

    async def unlock(self, tag: str | None = None) -> None:
        """Unlock the door."""
        if self.read_only:
            raise HomeAssistantError("Sesame 5 当前处于只读模式，已禁止远程解锁操作。如需操作，请在集成选项中关闭只读模式。")
        await self._ensure_connected()
        await self._device.unlock(tag or self.history_tag)

    async def toggle(self, tag: str | None = None) -> None:
        """Toggle lock state."""
        if self.read_only:
            raise HomeAssistantError("Sesame 5 当前处于只读模式，已禁止远程操作。如需操作，请在集成选项中关闭只读模式。")
        await self._ensure_connected()
        await self._device.toggle(tag or self.history_tag)

    def start_periodic_refresh(self) -> None:
        """Configure periodic status polling if enabled by user."""
        if not self.config_entry:
            return

        interval_minutes = self.config_entry.options.get(
            CONF_REFRESH_INTERVAL,
            self.config_entry.data.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL),
        )

        if interval_minutes and interval_minutes > 0:
            self.update_interval = timedelta(minutes=interval_minutes)
            LOGGER.info("[%s] Periodic refresh set to every %d minutes", self.address, interval_minutes)
        else:
            self.update_interval = None
            LOGGER.info("[%s] Periodic refresh disabled (on-demand connection only)", self.address)

    def restart_periodic_refresh(self) -> None:
        """Restart periodic timer after option change."""
        self.start_periodic_refresh()

    async def shutdown(self) -> None:
        """Disconnect BLE device cleanly."""
        self._device.remove_update_callback(self._on_device_update)
        await self._device.disconnect()
