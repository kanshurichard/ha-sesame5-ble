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
    CONF_CONNECTION_MODE,
    CONF_HISTORY_TAG,
    CONF_LINKED_LOCK,
    CONF_READ_ONLY,
    CONF_REFRESH_INTERVAL,
    CONNECTION_MODE_POWER_SAVING,
    CONNECTION_MODE_REALTIME,
    DEFAULT_CONNECTION_MODE,
    DEFAULT_HISTORY_TAG,
    DEFAULT_LINKED_LOCK,
    DEFAULT_READ_ONLY,
    DEFAULT_REFRESH_INTERVAL,
    POWER_SAVING_IDLE_TIMEOUT,
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
    passcode_count: int = 0
    fingerprint_count: int = 0
    card_count: int = 0
    door_open: bool | None = None


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
        self._is_shutting_down = False
        self._reconnect_task: asyncio.Task[None] | None = None
        self._idle_disconnect_unsub: Callable[[], None] | None = None

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
    def connection_mode(self) -> str:
        """Return 'realtime' or 'power_saving'."""
        if self._device.is_keypad:
            return CONNECTION_MODE_POWER_SAVING
        if self.config_entry:
            return self.config_entry.options.get(
                CONF_CONNECTION_MODE,
                self.config_entry.data.get(CONF_CONNECTION_MODE, DEFAULT_CONNECTION_MODE),
            )
        return DEFAULT_CONNECTION_MODE

    @property
    def is_realtime_mode(self) -> bool:
        """Return True if persistent BLE long connection is enabled."""
        if self._device.is_keypad:
            return False
        return self.connection_mode == CONNECTION_MODE_REALTIME

    @property
    def linked_lock(self) -> str:
        """Return address of linked lock or 'auto'."""
        if self.config_entry:
            return self.config_entry.options.get(
                CONF_LINKED_LOCK,
                self.config_entry.data.get(CONF_LINKED_LOCK, DEFAULT_LINKED_LOCK),
            )
        return DEFAULT_LINKED_LOCK

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
            passcode_count=self._device.passcode_count,
            fingerprint_count=self._device.fingerprint_count,
            card_count=self._device.card_count,
            door_open=self._device.door_open,
        )

    async def _async_update_data(self) -> Sesame5State:
        """Fetch latest state from device via BLE."""
        try:
            await self._ensure_connected()
        except Exception as err:
            raise UpdateFailed(f"Unable to refresh Sesame 5 state: {err}") from err
        finally:
            self._schedule_power_saving_disconnect()
        return self._current_state

    def _on_device_update(self) -> None:
        """Callback from device when notification is processed or transport disconnects."""
        self.async_set_updated_data(self._current_state)
        if self._device.history:
            try:
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_SESAME_HISTORY_UPDATE,
                    {"address": self.address, "history": self._device.history},
                )
            except Exception:
                pass

        # In realtime mode, auto-reconnect if connection drops
        if self.is_realtime_mode and not self._device.is_connected and not self._is_shutting_down:
            self._trigger_reconnect()

    def _safe_create_task(self, coro: Any) -> Any:
        """Create async task safely on HA event loop from any thread."""
        loop = getattr(self.hass, "loop", None)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if loop and isinstance(loop, asyncio.AbstractEventLoop) and loop.is_running():
            if running_loop is loop:
                if hasattr(self.hass, "async_create_task"):
                    return self.hass.async_create_task(coro)
                return asyncio.create_task(coro)
            return asyncio.run_coroutine_threadsafe(coro, loop)

        if hasattr(self.hass, "async_create_task"):
            return self.hass.async_create_task(coro)
        return asyncio.create_task(coro)

    def _trigger_reconnect(self) -> None:
        """Schedule reconnection loop for persistent connection."""
        if self._is_shutting_down or not self.is_realtime_mode:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = self._safe_create_task(self._async_reconnect_loop())

    async def _async_reconnect_loop(self) -> None:
        """Keep-alive reconnect loop with exponential backoff for persistent connection."""
        delay = 3
        while not self._is_shutting_down and self.is_realtime_mode:
            if self._device.is_ready:
                break
            try:
                LOGGER.debug("[%s] Reconnecting persistent BLE connection...", self.address)
                async with self._connection_lock:
                    if not self._device.is_ready:
                        await self._device.authenticate()
                LOGGER.info("[%s] Persistent BLE connection re-established", self.address)
                break
            except Exception as err:
                LOGGER.debug("[%s] Persistent reconnect attempt failed: %s (retrying in %ds)", self.address, err, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    def _schedule_power_saving_disconnect(self, delay: float = POWER_SAVING_IDLE_TIMEOUT) -> None:
        """In power-saving mode, disconnect after a short idle timeout."""
        if self.is_realtime_mode or self._is_shutting_down:
            return
        if self._idle_disconnect_unsub:
            self._idle_disconnect_unsub()
            self._idle_disconnect_unsub = None

        def _do_disconnect(now: Any) -> None:
            self._idle_disconnect_unsub = None
            if not self.is_realtime_mode and self._device.is_connected:
                LOGGER.debug("[%s] Power saving mode: disconnecting after %ds idle timeout", self.address, delay)
                self._safe_create_task(self._device.disconnect())

        def _schedule() -> None:
            try:
                self._idle_disconnect_unsub = async_call_later(self.hass, delay, _do_disconnect)
            except Exception:
                pass

        loop = getattr(self.hass, "loop", None)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if loop and isinstance(loop, asyncio.AbstractEventLoop) and loop.is_running():
            if running_loop is loop:
                _schedule()
            else:
                loop.call_soon_threadsafe(_schedule)
        else:
            _schedule()

    def _on_history_broadcast(self, data: Any) -> None:
        """Handle history record broadcast from any lock in HA to detect password unlock."""
        # Keypads only: Locks do not need to process one-time passcode cleanup
        if not self._device.is_keypad:
            return

        lock_address = None
        history: Sesame5HistoryRecord | None = None
        if isinstance(data, dict):
            lock_address = data.get("address")
            history = data.get("history")
        elif isinstance(data, Sesame5HistoryRecord):
            history = data

        if not history or history.action != "unlock" or history.history_tag_type != HistoryTagType.PASSWORD:
            return

        # Check lock binding
        linked = self.linked_lock
        if linked and linked != DEFAULT_LINKED_LOCK:
            if not lock_address or lock_address.strip().lower() != linked.strip().lower():
                LOGGER.debug(
                    "[%s] Ignoring unlock from %s because linked lock is %s",
                    self.address,
                    lock_address,
                    linked,
                )
                return

        LOGGER.info(
            "[%s] Detected password unlock event from lock %s (tag: %s), checking one-time passcodes",
            self.address,
            lock_address or "unknown",
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

        # Fallback: if tag_name did not match specific passcode name/code, auto-delete the first active one-time passcode
        if not to_delete and self._temp_passcodes:
            for code, info in list(self._temp_passcodes.items()):
                if info.get("one_time"):
                    to_delete.append(code)
                    break

        for code in to_delete:
            LOGGER.info("[%s] Auto-deleting one-time passcode '%s' after unlock", self.address, code)
            self._safe_create_task(self.async_delete_passcode(code))

    async def _ensure_connected(self) -> None:
        """Ensure active and authenticated BLE connection to lock."""
        if self._idle_disconnect_unsub:
            self._idle_disconnect_unsub()
            self._idle_disconnect_unsub = None

        async with self._connection_lock:
            if self._device.is_ready:
                return

            LOGGER.debug("[%s] Coordinator establishing connection", self.address)
            await self._device.authenticate()

    async def lock(self, tag: str | None = None) -> None:
        """Lock the door."""
        if self.read_only:
            raise HomeAssistantError("Sesame 5 当前处于只读模式，已禁止远程施锁操作。如需操作，请在集成选项中关闭只读模式。")
        try:
            await self._ensure_connected()
            await self._device.lock(tag or self.history_tag)
        finally:
            self._schedule_power_saving_disconnect()

    async def unlock(self, tag: str | None = None) -> None:
        """Unlock the door."""
        if self.read_only:
            raise HomeAssistantError("Sesame 5 当前处于只读模式，已禁止远程解锁操作。如需操作，请在集成选项中关闭只读模式。")
        try:
            await self._ensure_connected()
            await self._device.unlock(tag or self.history_tag)
        finally:
            self._schedule_power_saving_disconnect()

    async def toggle(self, tag: str | None = None) -> None:
        """Toggle lock state."""
        if self.read_only:
            raise HomeAssistantError("Sesame 5 当前处于只读模式，已禁止远程操作。如需操作，请在集成选项中关闭只读模式。")
        try:
            await self._ensure_connected()
            await self._device.toggle(tag or self.history_tag)
        finally:
            self._schedule_power_saving_disconnect()

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

        try:
            await self._ensure_connected()
            await self._device.add_passcode(passcode, name)
        finally:
            self._schedule_power_saving_disconnect()

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
                self._safe_create_task(self.async_delete_passcode(passcode))

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

        try:
            await self._ensure_connected()
            await self._device.delete_passcode(passcode)
        finally:
            self._schedule_power_saving_disconnect()

    async def async_get_passcodes(self) -> list[dict[str, Any]]:
        """Return list of passcodes registered on the device."""
        try:
            await self._ensure_connected()
            return await self._device.request_passcodes()
        finally:
            self._schedule_power_saving_disconnect()

    def start_periodic_refresh(self) -> None:
        """Configure periodic status polling if in power-saving mode."""
        if not self.config_entry or self.is_realtime_mode or self._device.is_keypad:
            self.update_interval = None
            return

        interval_minutes = self.config_entry.options.get(
            CONF_REFRESH_INTERVAL,
            self.config_entry.data.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL),
        )

        if interval_minutes and interval_minutes > 0:
            self.update_interval = timedelta(minutes=interval_minutes)
            LOGGER.info("[%s] Periodic refresh set to every %d minutes (Power-Saving Mode)", self.address, interval_minutes)
        else:
            self.update_interval = None
            LOGGER.info("[%s] Periodic refresh disabled (On-demand only)", self.address)

    def restart_periodic_refresh(self) -> None:
        """Restart periodic timer after option change."""
        self.start_periodic_refresh()

    def apply_options_update(self) -> None:
        """Apply updated connection mode and options from options flow."""
        LOGGER.info(
            "[%s] Applying updated options: mode=%s, read_only=%s",
            self.address,
            self.connection_mode,
            self.read_only,
        )
        if self.is_realtime_mode:
            if self._idle_disconnect_unsub:
                self._idle_disconnect_unsub()
                self._idle_disconnect_unsub = None
            self.update_interval = None
            if not self._device.is_ready:
                self._trigger_reconnect()
        else:
            if self._reconnect_task and not self._reconnect_task.done():
                self._reconnect_task.cancel()
            self.start_periodic_refresh()
            self._schedule_power_saving_disconnect(delay=3)

    async def shutdown(self) -> None:
        """Disconnect BLE device cleanly and cancel timers."""
        self._is_shutting_down = True

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()

        if self._idle_disconnect_unsub:
            self._idle_disconnect_unsub()
            self._idle_disconnect_unsub = None

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
