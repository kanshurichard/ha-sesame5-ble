"""DataUpdateCoordinator for Sesame 5 BLE integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HISTORY_TAG,
    CONF_READ_ONLY,
    CONF_REFRESH_INTERVAL,
    DEFAULT_HISTORY_TAG,
    DEFAULT_READ_ONLY,
    DEFAULT_REFRESH_INTERVAL,
    SIGNAL_SESAME_HISTORY_UPDATE,
)
from .device import Sesame5Device
from .helpers import (
    HistoryTagType,
    Sesame5HistoryRecord,
    Sesame5MechSetting,
    Sesame5MechStatus,
)

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
        self._temp_passcodes: dict[str, dict[str, Any]] = {}
        self._unsub_dispatcher: Callable[[], None] | None = None

        super().__init__(
            hass,
            LOGGER,
            name=f"Sesame 5 BLE ({device.address})",
            config_entry=entry,
            update_interval=None,
        )

        self._device.add_update_callback(self._on_device_update)

        try:
            self._unsub_dispatcher = async_dispatcher_connect(
                hass,
                SIGNAL_SESAME_HISTORY_UPDATE,
                self._on_history_broadcast,
            )
        except Exception:
            self._unsub_dispatcher = None

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
        if self._device.history:
            try:
                async_dispatcher_send(self.hass, SIGNAL_SESAME_HISTORY_UPDATE, self._device.history)
            except Exception:
                pass

    def _on_history_broadcast(self, history: Sesame5HistoryRecord) -> None:
        """Handle history record broadcast from any lock in HA to detect password unlock."""
        if history.action == "unlock" and history.history_tag_type == HistoryTagType.PASSWORD:
            LOGGER.info(
                "[%s] Detected password unlock event (tag: %s), checking one-time passcodes",
                self.address,
                history.tag_name or "unknown",
            )
            self.handle_one_time_unlock(history.tag_name)

    def handle_one_time_unlock(self, tag_name: str | None = None) -> None:
        """Auto-delete any registered one-time passcodes matching the unlock event."""
        to_delete: list[str] = []
        for code, info in list(self._temp_passcodes.items()):
            if not info.get("one_time"):
                continue
            if tag_name:
                if info.get("name") == tag_name or code == tag_name:
                    to_delete.append(code)
            else:
                # If no tag name reported by lock history, auto-delete first active one-time passcode
                to_delete.append(code)
                break

        for code in to_delete:
            LOGGER.info("[%s] Auto-deleting one-time passcode '%s' after unlock", self.address, code)
            self.hass.async_create_task(self.async_delete_passcode(code))

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

    async def async_add_passcode(
        self,
        passcode: str,
        name: str = "HA Temp",
        duration: int | None = None,
        one_time: bool = False,
    ) -> None:
        """Add a permanent, temporary, or one-time passcode to the keypad."""
        if self.read_only:
            raise HomeAssistantError("Sesame 当前处于只读模式，已禁止修改键盘密码。如需操作，请在集成选项中关闭只读模式。")

        await self._ensure_connected()
        await self._device.add_passcode(passcode, name)

        # Cancel any previous timer for this passcode
        if passcode in self._temp_passcodes:
            old_unsub = self._temp_passcodes[passcode].get("unsub")
            if callable(old_unsub):
                old_unsub()

        unsub = None
        if duration and duration > 0:
            def _auto_delete_timer(now: Any) -> None:
                LOGGER.info(
                    "[%s] Temporary passcode '%s' expired (%ds), auto-deleting",
                    self.address,
                    passcode,
                    duration,
                )
                self.hass.async_create_task(self.async_delete_passcode(passcode))

            unsub = async_call_later(self.hass, duration, _auto_delete_timer)

        self._temp_passcodes[passcode] = {
            "name": name,
            "duration": duration,
            "one_time": one_time,
            "unsub": unsub,
        }
        LOGGER.info(
            "[%s] Passcode '%s' registered (name='%s', duration=%s, one_time=%s)",
            self.address,
            passcode,
            name,
            duration,
            one_time,
        )

    async def async_delete_passcode(self, passcode: str) -> None:
        """Delete a passcode from the keypad and cancel timers."""
        if self.read_only:
            raise HomeAssistantError("Sesame 当前处于只读模式，已禁止删除键盘密码。如需操作，请在集成选项中关闭只读模式。")

        if passcode in self._temp_passcodes:
            unsub = self._temp_passcodes.pop(passcode).get("unsub")
            if callable(unsub):
                unsub()

        await self._ensure_connected()
        await self._device.delete_passcode(passcode)

    async def async_get_passcodes(self) -> list[dict[str, Any]]:
        """Return list of passcodes registered on the device."""
        await self._ensure_connected()
        return await self._device.request_passcodes()

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
        """Disconnect BLE device cleanly and cancel timers."""
        if self._unsub_dispatcher:
            self._unsub_dispatcher()
            self._unsub_dispatcher = None

        for code, info in list(self._temp_passcodes.items()):
            unsub = info.get("unsub")
            if callable(unsub):
                unsub()
        self._temp_passcodes.clear()

        self._device.remove_update_callback(self._on_device_update)
        await self._device.disconnect()
